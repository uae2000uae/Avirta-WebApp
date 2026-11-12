"""
Flask web application for Avirta game.

This module provides a web interface for the Avirta game, allowing users to
access and play the game through a web browser.
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, send_file, jsonify, current_app
import os
import sys
import tempfile
import uuid
import random
import json
import time
import secrets
from datetime import datetime

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import modules
from contents.admin_controls.admin_setup import AdminSetup
from questionmanagement.categories_questions.category_manager import CategoryManager
from questionmanagement.categories_questions.question_uploader import QuestionUploader
from contents.game_room.game_room import GameRoom
from contents.game_room.game_status_manager import GameStatusManager, add_game_event, set_game_status_manager, set_stats_sink
from questionmanagement.question_manager import QuestionManager
from questionmanagement.bulk_upload.bulk_import import BulkImport
from questionmanagement.reported_questions.reported_question_manager import ReportedQuestionManager
from contents.thehive.thehive import register_hive_routes
from contents.fastest.fastest import register_fastest_routes
from questionmanagement.question_bank import QuestionBank, increment_use_count, set_question_bank_instance
from questionmanagement.question_import_export import export_template
from questionmanagement.ai_engine.batches import get_batch, get_batch_metadata, get_all_batches
from contents.admin_controls.ai_routes import register_ai_routes

# Create Flask application
app = Flask(__name__, static_url_path='/static', template_folder="templates")

# Secret key for signing session cookies.
# Resolution order: SECRET_KEY env var / Google Secret Manager (via get_secret),
# then FLASK_SECRET_KEY env var, then an ephemeral random key as a last resort.
# Never commit a real key to source. In production, set a "SECRET_KEY" secret
# (see cloudbuild.yaml --set-secrets) so sessions survive restarts.
try:
    from contents.admin_controls.secret_loader import get_secret as _get_secret
    _resolved_secret_key = _get_secret('SECRET_KEY')
except Exception:
    _resolved_secret_key = None

_resolved_secret_key = _resolved_secret_key or os.environ.get('FLASK_SECRET_KEY')

if not _resolved_secret_key:
    _resolved_secret_key = secrets.token_hex(32)
    print(
        "WARNING: No SECRET_KEY configured; using an ephemeral random key. "
        "Sessions will reset on restart and will not be shared across instances. "
        "Set a SECRET_KEY secret/env var for production."
    )

app.secret_key = _resolved_secret_key

# Harden session cookies.
# Only mark the session cookie "Secure" when we're actually served over HTTPS
# (i.e. running on Cloud Run, which sets K_SERVICE). A Secure cookie is dropped
# by browsers over plain HTTP, which silently breaks sessions — and therefore
# CSRF validation — during local development on http://localhost. Basing this on
# the real environment (rather than FLASK_DEBUG) means local dev works without
# any extra env vars, while production stays secure. Force-disable with
# SESSION_COOKIE_INSECURE=1 or when FLASK_DEBUG=1.
_on_cloud_run = bool(os.environ.get('K_SERVICE'))
_force_insecure = (
    os.environ.get('SESSION_COOKIE_INSECURE', '0') == '1'
    or os.environ.get('FLASK_DEBUG', '0') == '1'
)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=_on_cloud_run and not _force_insecure,
)


@app.after_request
def set_security_headers(response):
    """Add baseline security headers to every response (dependency-free)."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    # HSTS is safe here because the public Cloud Run URL is always HTTPS.
    response.headers.setdefault(
        'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
    )
    return response


# --- CSRF protection (dependency-free, session-based) ---
import hmac

_CSRF_SESSION_KEY = '_csrf_token'
_CSRF_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}


def _get_or_create_csrf_token():
    """Return the session CSRF token, creating one if needed."""
    token = session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        session[_CSRF_SESSION_KEY] = token
    return token


def csrf_exempt(view):
    """Decorator to exempt a specific view function from CSRF checks."""
    view._csrf_exempt = True
    return view


@app.context_processor
def _inject_csrf_token():
    # Exposes {{ csrf_token }} to every template and ensures the token exists.
    return {'csrf_token': _get_or_create_csrf_token()}


def _extract_submitted_csrf_token():
    # Accept the token from a form field or from common request headers
    # (used by fetch/XHR requests that send JSON or FormData bodies).
    token = request.form.get('csrf_token')
    if not token:
        token = (
            request.headers.get('X-CSRFToken')
            or request.headers.get('X-CSRF-Token')
            or request.headers.get('X-Csrf-Token')
        )
    return token


@app.before_request
def _csrf_protect():
    """Reject state-changing requests that lack a valid CSRF token."""
    if request.method in _CSRF_SAFE_METHODS:
        return None
    view = app.view_functions.get(request.endpoint)
    if view is not None and getattr(view, '_csrf_exempt', False):
        return None
    expected = session.get(_CSRF_SESSION_KEY)
    submitted = _extract_submitted_csrf_token()
    if (
        not expected
        or not submitted
        or not hmac.compare_digest(str(expected), str(submitted))
    ):
        return jsonify({'error': 'Invalid or missing CSRF token'}), 400
    return None


# Add template filter to detect Arabic text
@app.template_filter('is_arabic')
def is_arabic(text):
    """
    Check if text contains Arabic characters.

    Args:
        text (str): The text to check

    Returns:
        bool: True if the text contains Arabic characters, False otherwise
    """
    if not text:
        return False

    # Arabic Unicode range (simplified)
    arabic_range = range(0x0600, 0x06FF)

    # Check if any character in the text is in the Arabic range
    for char in text:
        if ord(char) in arabic_range:
            return True

    return False

# Add enumerate function to Jinja2 environment
app.jinja_env.globals.update(enumerate=enumerate)

# Initialize game components
admin_setup = AdminSetup()


def _record_sync_event(level, message, detail):
    """Record GitHub sync results in the admin log and stats."""
    if level == 'ERROR':
        admin_setup.record_stat('github_push_failures')
        admin_setup.log_event(message, level='ERROR', category='GITHUB', reasons=detail)
    elif level == 'SUCCESS':
        admin_setup.record_stat('github_auto_pushes')
        admin_setup.log_event(message, level='SUCCESS', category='GITHUB', reasons=detail)


from contents.admin_controls import github_sync as _github_sync  # noqa: E402
_github_sync.set_event_hook(_record_sync_event)


def _request_github_sync(reason):
    """Queue a GitHub sync of all changed app data and watch it from this browser."""
    try:
        session['sync_watch'] = time.time()
    except RuntimeError:
        pass  # outside a request
    try:
        return _github_sync.request_sync(reason)
    except Exception as exc:  # never break the calling request
        admin_setup.log_event(f"Could not start GitHub sync: {exc}", level='ERROR', category='GITHUB')
        return False, f"Could not start GitHub sync: {exc}"
category_manager = CategoryManager()
questions_dir = os.path.join(os.path.dirname(__file__), "contents", "questions")
question_uploader = QuestionUploader(questions_dir)
bulk_import = BulkImport(question_uploader, category_manager)
question_bank = QuestionBank(questions_dir)
# Update the singleton instance to use the custom instance with the correct path
set_question_bank_instance(question_bank)
reported_questions_dir = os.path.join(os.path.dirname(__file__), "questionmanagement", "reported_questions")
reported_question_manager = ReportedQuestionManager(reported_questions_dir)

# ANSI escape codes for red text (assuming '.error' means red styling)
ERROR_STYLE = "\033[91m"  # Red color
RESET_STYLE = "\033[0m"   # Reset to default

# Categories are now dynamically derived from questions in the database
# as per PRJ-003 rule, so we don't add default categories here

# Load existing questions
question_uploader.load_questions()

# Remove any duplicate questions
num_duplicates = question_uploader.remove_duplicate_questions()
if num_duplicates > 0:
    print(f"Removed {num_duplicates} duplicate questions")

# Load question_bank with the latest data after removing duplicates
question_bank.load_questions()

# Add an admin user
admin_setup.add_admin("admin", "ADMIN")

# Active game rooms. Behaves like a dict; on Cloud Run (ROOM_STORE=firestore)
# every room a request changes is saved to Firestore and reloaded after a
# restart or redeploy, so live games survive deploys.
from contents.game_room.room_store import PersistentRooms, backend_from_env
game_rooms = PersistentRooms(backend_from_env())


@app.before_request
def _rooms_begin_request():
    game_rooms.begin_request()


@app.teardown_request
def _rooms_end_request(_exc=None):
    game_rooms.end_request()

# Create a centralized game status manager for real-time updates with persistence
events_dir = os.path.join(os.path.dirname(__file__), 'contents', 'game_events')
game_status_manager = GameStatusManager(max_events_per_room=100, persistence_dir=events_dir)

# Set the global GameStatusManager instance
set_game_status_manager(game_status_manager)

# Feed gameplay events into the admin stats dashboard (in-memory counters/logs)
set_stats_sink(admin_setup)

# Register The Hive routes in a separate module to keep app.py clean
register_hive_routes(app, game_rooms, game_status_manager, question_uploader, add_game_event)

# Register Fastest game routes in a separate module to keep app.py clean
register_fastest_routes(app, game_rooms, game_status_manager, question_uploader, add_game_event, admin_setup)

@app.route('/')
def index():
    """Render the home page."""
    return render_template('index.html')

@app.route('/ping')
def ping():
    """Simple endpoint to check if the server is running."""
    response = make_response("pong")
    # Add CORS headers to allow access from any origin
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response


@app.route('/api/game_updates/<room_id>')
def game_updates(room_id):
    """
    Get the latest game updates for a room.

    As per PRJ-006, this endpoint serves as the centralized source of game state information,
    providing consistent updates to all connected clients.

    Returns:
        JSON with the current game state, recent events, and game statistics
    """
    # Check if the room exists in memory
    if room_id not in game_rooms:
        # Try to load it from persistence
        game_room = game_status_manager.load_game_room(room_id)
        if game_room:
            # Add it to the in-memory dictionary
            game_rooms[room_id] = game_room
        else:
            return jsonify({'error': 'Game room not found'}), 404

    # Check if the player is in the session
    if 'player_name' not in session:
        return jsonify({'error': 'Player not in session'}), 401

    # Get the game room and player name
    game_room = game_rooms[room_id]
    player_name = session['player_name']

    # Check if the player is in the room
    if player_name not in game_room.players:
        return jsonify({'error': 'Player not in room'}), 403

    # Get the current player (whose turn it is)
    current_player = game_room.current_player

    # Get the player tools - always get tools for the requesting player
    # This ensures each player has their own unique set of tools
    player_tools = game_room.get_player_tools(player_name)

    # If the player is the host, also include the current player's tools for reference
    # but keep them separate from the host's own tools
    current_player_tools = None
    if game_room.is_host(player_name) and current_player != player_name:
        current_player_tools = game_room.get_player_tools(current_player)

    # Get the leaderboard
    leaderboard = []
    if hasattr(game_room, 'question_manager'):
        leaderboard = game_room.question_manager.get_leaderboard(all_players=game_room.players)

    # Get the recent events for this room from the centralized game status manager
    events = game_status_manager.get_events(room_id)

    # Get player-specific events if requested
    player_events = None
    if request.args.get('include_player_events') == 'true':
        player_events = game_status_manager.get_events_by_player(room_id, player_name)

    # Get room statistics
    room_stats = None
    if request.args.get('include_stats') == 'true' or game_room.is_host(player_name):
        room_stats = game_status_manager.get_room_statistics(room_id)

    # Get the latest events by type for key game state information
    latest_events = {}
    for event_type in ['game_started', 'turn_switch', 'question_selected', 'game_ended']:
        latest_event = game_status_manager.get_latest_event_by_type(room_id, event_type)
        if latest_event:
            latest_events[event_type] = latest_event

    # Get the current question if available
    current_question = None
    if 'current_question' in session:
        current_question = session['current_question']

    # Check if a question is currently active
    host_on_question_page = game_room.question_active

    # Get available questions for the game board (only for host)
    available_questions = None
    if game_room.is_host(player_name):
        available_questions = game_room.get_available_questions()

    # Return the game state and events
    response_data = {
        'current_player': current_player,
        'is_current_player_turn': (player_name == current_player),
        'is_host': game_room.is_host(player_name),
        'player_tools': player_tools,
        'players': game_room.players,
        'leaderboard': leaderboard,
        'events': events,
        'current_question': current_question,
        'host_on_question_page': host_on_question_page,
        'available_questions': available_questions,
        'latest_events': latest_events
    }

    # Include current player's tools if the player is the host
    if current_player_tools is not None:
        response_data['current_player_tools'] = current_player_tools

    # Add optional data if requested
    if player_events is not None:
        response_data['player_events'] = player_events

    if room_stats is not None:
        response_data['room_stats'] = room_stats

    return jsonify(response_data)

@app.route('/create_room', methods=['GET', 'POST'])
def create_room():
    """Create a new game room."""
    if request.method == 'POST':
        room_name = request.form.get('room_name')
        host_name = request.form.get('host_name')
        selected_categories = request.form.getlist('categories')
        additional_players = request.form.getlist('additional_players')
        selected_question_types = request.form.getlist('question_types')

        if not room_name or not host_name or not selected_question_types:
            session['error_modal'] = 'Please fill in all fields and select at least one question type.'
            return redirect(url_for('create_room'))

        # If no categories selected, default to all available categories
        if not selected_categories:
            categories_dict = get_categories_with_questions()
            selected_categories = list(categories_dict.keys())

        # Limit to max_categories_per_room (default is 7)
        max_categories = admin_setup.game_settings.get('max_categories_per_room', 7)
        selected_categories = selected_categories[:max_categories]

        # Create a unique room ID
        room_id = f"room_{uuid.uuid4().hex[:8]}"

        # Create the game room with question types
        game_room = GameRoom(room_id, room_name, host_name, selected_categories, question_types=selected_question_types)

        # Get the maximum number of players per room from admin settings
        max_players = admin_setup.game_settings.get('max_players_per_room', 10)

        # Add additional players to the room, limited by max_players
        player_count = 1  # Start with 1 for the host
        for player_name in additional_players:
            if player_name and player_name.strip():  # Only add non-empty player names
                if player_count < max_players:  # Check if we've reached the maximum
                    game_room.add_player(player_name.strip())
                    player_count += 1
                else:
                    session['error_modal'] = f'Maximum number of players ({max_players}) reached. Some players were not added.'
                    break

        # Reload questions from disk to ensure we have the latest data
        question_uploader.load_questions()

        # Remove any duplicate questions
        question_uploader.remove_duplicate_questions()

        # Create the game board with configurable number of questions per category
        questions_per_category = admin_setup.game_settings.get('questions_per_category', 10)
        success, enough_questions, error_details = game_room.create_board(question_uploader, questions_per_category)

        # Check if there were enough questions that matched the criteria
        if not enough_questions:
            # Use detailed error message from the sophisticated algorithm
            detailed_message = error_details.get('overall_message', 'Couldn\'t find enough questions of the selected criteria.')
            # Convert newlines to HTML breaks for proper display in modal
            detailed_message_html = detailed_message.replace('\n', '<br>')
            session['error_modal'] = detailed_message_html
            return redirect(url_for('create_room'))

        # Store the game room
        game_rooms[room_id] = game_room

        # Persist the game room to disk
        game_status_manager.persist_game_room(room_id, game_room)

        # Store the room ID in the session
        session['room_id'] = room_id
        session['player_name'] = host_name

        # Add a game event for the game starting
        add_game_event(room_id, 'game_started', {
            'player_name': host_name,
            'message': f'Game started by {host_name}',
            'categories': selected_categories,
            'question_types': selected_question_types,
            'players': game_room.players
        })

        return redirect(url_for('game_room', room_id=room_id))

    # GET request
    categories = get_categories_with_questions()
    # Get the maximum number of players per room from admin settings
    max_players = admin_setup.game_settings.get('max_players_per_room', 10)
    # Get the maximum number of categories per room from admin settings
    max_categories = admin_setup.game_settings.get('max_categories_per_room', 7)
    return render_template('Columns/create_room.html', categories=categories, max_players=max_players, max_categories=max_categories)



@app.route('/join_room', methods=['GET', 'POST'])
def join_room():
    """Join an existing game room."""
    if request.method == 'POST':
        room_id = request.form.get('room_id')
        player_name = request.form.get('player_name')

        if not room_id or not player_name:
            flash('Please fill in all fields.')
            return redirect(url_for('join_room'))

        # Check if the room exists in memory
        if room_id not in game_rooms:
            # Try to load it from persistence
            game_room = game_status_manager.load_game_room(room_id)
            if game_room:
                # Add it to the in-memory dictionary
                game_rooms[room_id] = game_room
            else:
                flash('Game room not found.')
                return redirect(url_for('join_room'))

        # Add the player to the room
        game_room = game_rooms[room_id]

        # Get the maximum number of players per room from admin settings
        max_players = admin_setup.game_settings.get('max_players_per_room', 10)

        # Check if the room is already at maximum capacity
        if len(game_room.players) >= max_players:
            flash(f'Game room is full. Maximum number of players ({max_players}) reached.')
            return redirect(url_for('join_room'))

        success = game_room.add_player(player_name)

        if not success:
            flash('<span class="error">Could not join the game room. You might already be in it.</span>', 'error')
            return redirect(url_for('join_room'))

        # Store the room ID and player name in the session
        session['room_id'] = room_id
        session['player_name'] = player_name

        # Persist the updated game room to disk
        game_status_manager.persist_game_room(room_id, game_room)

        # Add a game event for the player joining
        add_game_event(room_id, 'player_joined', {
            'player_name': player_name,
            'message': f'{player_name} joined the room'
        })

        return redirect(url_for('joined_room', room_id=room_id))

    # GET request
    return render_template('Columns/join_room.html')

@app.route('/joined_room/<room_id>')
def joined_room(room_id):
    """View a joined game room without the questions grid."""
    # Check if the room exists
    if room_id not in game_rooms:
        flash('Game room not found.')
        return redirect(url_for('index'))

    # Check if the player is in the session
    if 'player_name' not in session:
        flash('Please join the game first.')
        return redirect(url_for('join_room'))

    # Get the game room and player name
    game_room = game_rooms[room_id]
    player_name = session['player_name']

    # Check if the player is in the room
    if player_name not in game_room.players:
        flash('You are not in this game room.')
        return redirect(url_for('join_room'))

    # Get the current player (whose turn it is)
    current_player = game_room.current_player

    # Get the player tools - if host, get tools for current player
    if game_room.is_host(player_name):
        player_tools = game_room.get_player_tools(current_player)
    else:
        player_tools = game_room.get_player_tools(player_name)

    # Check if it's the current player's turn
    is_current_player_turn = (player_name == current_player)

    # Check if the player is the host
    is_host = game_room.is_host(player_name)

    # Get the leaderboard
    leaderboard = []
    if hasattr(game_room, 'question_manager'):
        leaderboard = game_room.question_manager.get_leaderboard(all_players=game_room.players)

    # Clear any acting_player from the session when viewing the joined room
    session.pop('acting_player', None)

    return render_template(
        'Columns/joined_room.html',
        room=game_room,
        player_name=player_name,
        player_tools=player_tools,
        current_player=current_player,
        is_current_player_turn=is_current_player_turn,
        is_host=is_host,
        leaderboard=leaderboard
    )

@app.route('/end_game/<room_id>')
def end_game(room_id):
    """End a game and return to the home page."""
    # Check if the room exists
    if room_id not in game_rooms:
        flash('Game room not found.')
        return redirect(url_for('index'))

    # Check if the player is in the session
    if 'player_name' not in session:
        flash('Please join the game first.')
        return redirect(url_for('index'))

    # Get the game room and player name
    game_room = game_rooms[room_id]
    player_name = session['player_name']

    # Determine participants list generically (supports modes without .players)
    participants = []
    try:
        participants = list(getattr(game_room, 'players')) if hasattr(game_room, 'players') else []
    except Exception:
        participants = []
    if not participants:
        # Fallback to teams (Hive)
        participants = list(getattr(game_room, 'teams', []))

    # If we have a participants list, validate membership
    if participants and player_name not in participants:
        flash('You are not in this game room.')
        return redirect(url_for('index'))

    # Determine host permission in a mode-agnostic way
    is_host_ok = False
    if hasattr(game_room, 'is_host'):
        try:
            is_host_ok = bool(game_room.is_host(player_name))
        except Exception:
            is_host_ok = False
    elif hasattr(game_room, 'host'):
        is_host_ok = (player_name == getattr(game_room, 'host', None))
    else:
        # Hive: allow only team_a (creator) to end the game
        team_a = getattr(game_room, 'team_a', None)
        is_host_ok = (team_a is None) or (player_name == team_a)

    if not is_host_ok:
        flash('Only the host can end the game.')
        return redirect(url_for('index'))


    # End the game
    game_room.end_game()

    # Add a game event for the game ending
    add_game_event(room_id, 'game_ended', {
        'player_name': player_name,
        'message': f'The game has been ended by the host ({player_name})'
    })

    # Sync all changed app data (usage counts, game logs, questions...) to GitHub.
    # Must run before cleanup_room_data(): the request captures this game's log
    # files, which are deleted just below.
    _request_github_sync(f"game ended ({room_id})")

    # Clean up room data (remove room and event files)
    game_status_manager.cleanup_room_data(room_id)

    # Remove the room from memory
    if room_id in game_rooms:
        del game_rooms[room_id]

    # Clear the room_id and player_name from the session
    session.pop('room_id', None)
    session.pop('player_name', None)

    flash('You have ended the game.')
    return redirect(url_for('index'))

@app.route('/leave_game/<room_id>')
def leave_game(room_id):
    """Leave a game room."""
    # Check if the room exists
    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    # Check if the player is in the session
    if 'player_name' not in session:
        flash('Please join the game first.', 'error')
        return redirect(url_for('join_room'))

    # Get the game room and player name
    game_room = game_rooms[room_id]
    player_name = session['player_name']

    # Check if the player is in the room
    if player_name not in game_room.players:
        flash('You are not in this game room.', 'error')
        return redirect(url_for('join_room'))

    # Check if it's the player's turn
    is_current_player_turn = (player_name == game_room.current_player)

    # Remove the player from the room
    success = game_room.remove_player(player_name)

    if not success:
        flash('Could not leave the game room.', 'error')
        return redirect(url_for('joined_room', room_id=room_id))

    # If it was the player's turn, advance to the next player
    if is_current_player_turn:
        game_room.advance_turn()

    # Add a game event for the player leaving
    add_game_event(room_id, 'player_left', {
        'player_name': player_name,
        'message': f'{player_name} left the room'
    })

    # Clear the room_id and player_name from the session
    session.pop('room_id', None)
    session.pop('player_name', None)

    flash('You have left the game room.')
    return redirect(url_for('index'))

@app.route('/game_room/<room_id>')
def game_room(room_id):
    """View a game room."""
    # Check if the room exists
    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    # Check if the player is in the session
    if 'player_name' not in session:
        flash('Please join the game first.', 'error')
        return redirect(url_for('join_room'))

    # Get the game room and player name
    game_room = game_rooms[room_id]
    player_name = session['player_name']

    # Check if the player is in the room
    if player_name not in game_room.players:
        flash('You are not in this game room.', 'error')
        return redirect(url_for('join_room'))

    # Check if the user is coming from the result page
    referrer = request.referrer
    if referrer and 'result' in referrer:
        # Get the current player before advancing the turn
        previous_player = game_room.current_player

        # Advance to the next player's turn
        game_room.advance_turn()

        # Get the new current player
        new_player = game_room.current_player

        # Add a game event for the turn switch
        add_game_event(room_id, 'turn_switch', {
            'previous_player': previous_player,
            'new_player': new_player,
            'message': f'Turn switched from {previous_player} to {new_player}'
        })

    # Get the available questions
    available_questions = game_room.get_available_questions()

    # Get the current player (whose turn it is)
    current_player = game_room.current_player

    # Get the player tools - if host, get tools for current player
    if game_room.is_host(player_name):
        player_tools = game_room.get_player_tools(current_player)
    else:
        player_tools = game_room.get_player_tools(player_name)

    # Check if it's the current player's turn
    is_current_player_turn = (player_name == current_player)

    # Check if the player is the host
    is_host = game_room.is_host(player_name)

    # Clear any acting_player from the session when viewing the game room
    session.pop('acting_player', None)

    # Determine which template to use based on the room_id
    template = 'Columns/game_room.html'

    return render_template(
        template,
        room=game_room,
        player_name=player_name,
        available_questions=available_questions,
        player_tools=player_tools,
        current_player=current_player,
        is_current_player_turn=is_current_player_turn,
        is_host=is_host
    )

@app.route('/select_question', methods=['POST'])
def select_question():
    """Select a question from the game board."""
    room_id = session.get('room_id')
    player_name = session.get('player_name')

    if not room_id or not player_name:
        flash('Please join a game first.', 'error')
        return redirect(url_for('index'))

    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    game_room = game_rooms[room_id]

    category_id = request.form.get('category_id')
    # Safely parse points to avoid server errors when missing/invalid
    points_raw = request.form.get('points')
    try:
        points = int(points_raw)
    except (TypeError, ValueError):
        flash('Invalid point value selected.', 'error')
        return redirect(url_for('game_room', room_id=room_id))

    # Check if the host is acting on behalf of another player
    acting_player = request.form.get('acting_player')

    # If acting_player is provided, store it in the session
    if acting_player:
        session['acting_player'] = acting_player

    # Select the question
    question_id = (request.form.get('question_id') or '').strip() or None
    question = game_room.select_question(category_id, points, player_name, acting_player, question_id)

    if not question:
        flash('Question not available.', 'error')
        return redirect(url_for('game_room', room_id=room_id))

    # Store the question in the session
    session['current_question'] = question

    # Set the question_active property to True
    game_room.question_active = True

    # Add a game event for the question selection
    points = question.get('points', 0)
    event_player = acting_player if acting_player else player_name
    add_game_event(room_id, 'question_selected', {
        'player_name': event_player,
        'category': category_id,
        'points': points,
        'message': f'{event_player} selected a {points}-point question from {category_id}'
    })

    return redirect(url_for('question', room_id=room_id))

@app.route('/question/<room_id>')
def question(room_id):
    """View a question."""
    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    if 'current_question' not in session:
        flash('No question selected.', 'error')
        return redirect(url_for('game_room', room_id=room_id))

    question = session['current_question']
    player_name = session.get('player_name')
    acting_player = session.get('acting_player')

    # Shuffle options for multiple-choice questions
    if question.get('type') == 'multiple_choice' and 'options' in question:
        # Create a copy of the options list and shuffle it
        shuffled_options = question['options'].copy()
        random.shuffle(shuffled_options)
        question['options'] = shuffled_options

    # Get the game room to check if the player is the host
    game_room = game_rooms[room_id]
    is_host = game_room.is_host(player_name)

    # Get the current player (whose turn it is)
    current_player = game_room.current_player

    # Get the player tools - if host, get tools for current player
    if game_room.is_host(player_name):
        player_tools = game_room.get_player_tools(current_player)
    else:
        # Only show tools if it's the player's turn
        if player_name == current_player:
            player_tools = game_room.get_player_tools(player_name)
        else:
            # If it's not the player's turn, don't show any tools
            player_tools = {}

    # Ensure player_tools has the expected structure for the template
    # The template expects player_tools.change_question to be a boolean
    if not player_tools:
        player_tools = {"change_question": False, "double_points": False}

    # Get the default time limit from admin settings
    default_time_limit = admin_setup.game_settings.get('default_time_limit', 30)

    # Create response with template
    response = make_response(render_template(
        'Columns/question.html',
        room_id=room_id,
        question=question,
        player_name=player_name,
        acting_player=acting_player,
        is_host=is_host,
        player_tools=player_tools,
        current_player=current_player
    ))

    # Set cookie with default time limit
    response.set_cookie('default_time_limit', str(default_time_limit))

    return response

@app.route('/answer_question', methods=['POST'])
def answer_question():
    """Submit an answer to a question."""
    room_id = session.get('room_id')
    player_name = session.get('player_name')
    acting_player = session.get('acting_player')

    if not room_id or not player_name:
        flash('Please join a game first.', 'error')
        return redirect(url_for('index'))

    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    if 'current_question' not in session:
        flash('No question selected.', 'error')
        return redirect(url_for('game_room', room_id=room_id))

    game_room = game_rooms[room_id]
    question = session['current_question']

    # Get the answer from the form
    answer = request.form.get('answer')

    # Determine the effective player (who will be credited with the answer)
    effective_player = player_name

    # If acting_player is provided and player_name is the host, use acting_player
    if acting_player and game_room.is_host(player_name) and acting_player in game_room.players:
        effective_player = acting_player

    # Create a question manager if it doesn't exist for this room
    if 'question_manager' not in game_room.__dict__:
        game_room.question_manager = QuestionManager()

    # Add the current question to the question manager's questions list
    if not game_room.question_manager.questions or game_room.question_manager.questions[-1].get('id') != question.get('id'):
        game_room.question_manager.questions.append(question)
        game_room.question_manager.current_question_index = len(game_room.question_manager.questions) - 1

    # Check the answer
    is_correct = game_room.question_manager.check_answer(effective_player, answer)

    # Note: Turn switching is now handled in the game_room route when returning from the result page

    # Define events with priority values (lower number = higher priority)
    event_priority = {
        1: ('answer_submitted', {
            'player_name': effective_player,
            'category': question.get('category_id', 'Unknown'),
            'points': question.get('points', 0),
            'is_correct': is_correct,
            'message': f'{effective_player} answered {"correct" if is_correct else "incorrect"} and earned {question.get("points", 0) if is_correct else 0} points'
        })
    }

    # Sort events by priority and process them in order
    for _, (event_name, event_data) in sorted(event_priority.items()):
        add_game_event(room_id, event_name, event_data)

    # Increment the use_count for this question
    if 'id' in question:
        increment_use_count(question['id'])

    # Clear the current question and acting_player from the session
    session.pop('current_question', None)
    session.pop('acting_player', None)

    # Set the question_active property to False
    game_room.question_active = False

    # Redirect to the result page
    return redirect(url_for('result', room_id=room_id, is_correct=is_correct))

@app.route('/evaluate_answer', methods=['POST'])
def evaluate_answer():
    """Evaluate an answer based on moderator's judgment."""
    room_id = session.get('room_id')
    player_name = session.get('player_name')
    acting_player = session.get('acting_player')

    if not room_id or not player_name:
        flash('Please join a game first.')
        return redirect(url_for('index'))

    if room_id not in game_rooms:
        flash('Game room not found.')
        return redirect(url_for('index'))

    if 'current_question' not in session:
        flash('No question selected.')
        return redirect(url_for('game_room', room_id=room_id))

    game_room = game_rooms[room_id]
    question = session['current_question']

    # Get the evaluation from the form
    evaluation = request.form.get('evaluation')
    is_correct = evaluation == 'correct'

    # Determine the effective player (who will be credited with the answer)
    effective_player = player_name

    # If acting_player is provided and player_name is the host, use acting_player
    if acting_player and game_room.is_host(player_name) and acting_player in game_room.players:
        effective_player = acting_player

    # Create a question manager if it doesn't exist for this room
    if 'question_manager' not in game_room.__dict__:
        game_room.question_manager = QuestionManager()

    # Add the current question to the question manager's questions list
    if not game_room.question_manager.questions or game_room.question_manager.questions[-1].get('id') != question.get('id'):
        game_room.question_manager.questions.append(question)
        game_room.question_manager.current_question_index = len(game_room.question_manager.questions) - 1

    # Update the player's score based on the evaluation
    if is_correct:
        # Award points to the effective player
        game_room.question_manager.award_points(effective_player, question.get('points', 0))

    # Increment the use_count of the question
    question_id = question.get('id')
    if question_id:
        increment_use_count(question_id)

    # Add a game event for the answer evaluation
    category_id = question.get('category_id', 'Unknown')
    points = question.get('points', 0)
    result_text = 'correct' if is_correct else 'incorrect'
    add_game_event(room_id, 'answer_evaluated', {
        'player_name': effective_player,
        'evaluator': player_name,
        'category': category_id,
        'points': points,
        'is_correct': is_correct,
        'message': f'The Host evaluated {effective_player}\'s answer as {result_text} and earned {points if is_correct else 0} points'
    })

    # Clear the current question and acting_player from the session
    session.pop('current_question', None)
    session.pop('acting_player', None)

    # Set the question_active property to False
    game_room.question_active = False

    # Redirect to the result page
    return redirect(url_for('result', room_id=room_id, is_correct=is_correct))

@app.route('/result/<room_id>')
def result(room_id):
    """View the result of answering a question."""
    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    is_correct = request.args.get('is_correct') == 'True'
    player_name = session.get('player_name')

    game_room = game_rooms[room_id]

    # Get the player's score
    score = 0
    leaderboard = []
    correct_answer = ""
    question_text = ""
    current_question = None

    if hasattr(game_room, 'question_manager'):
        score = game_room.question_manager.get_player_score(player_name)
        leaderboard = game_room.question_manager.get_leaderboard(all_players=game_room.players)

        # Get the correct answer from the most recent question
        if game_room.question_manager.questions and game_room.question_manager.current_question_index >= 0:
            current_question = game_room.question_manager.questions[game_room.question_manager.current_question_index]
            correct_answer = current_question.get('correct_answer', '')
            question_text = current_question.get('question', '')

    # Determine which template to use based on the room_id
    template = 'result.html'

    return render_template(
        template,
        room_id=room_id,
        is_correct=is_correct,
        player_name=player_name,
        score=score,
        leaderboard=leaderboard,
        correct_answer=correct_answer,
        question_text=question_text,
        current_player=game_room.current_player,
        current_question=current_question
    )


@app.route('/report_question', methods=['POST'])
def report_question():
    """Report a question for review.

    Behaviors:
    - Standard form POST: flashes a message and redirects to result page (legacy behavior)
    - AJAX/JSON POST (X-Requested-With=XMLHttpRequest or Accept includes application/json):
      returns JSON and does not redirect, so the client can keep the user on the same page.
    """
    question_id = request.form.get('question_id')
    room_id = request.form.get('room_id')
    player_name = session.get('player_name')
    is_correct = request.form.get('is_correct', 'False')

    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in (request.headers.get('Accept') or '')
    )

    if not question_id or not room_id:
        if wants_json:
            return jsonify({'success': False, 'message': 'Invalid request: missing question or room id.'}), 400
        flash('Invalid request.', 'error')
        return redirect(url_for('index'))

    # Get the question data from the question_uploader
    question_data = question_uploader.get_question(question_id)

    if not question_data:
        if wants_json:
            return jsonify({'success': False, 'message': 'Question not found.'}), 404
        flash('Question not found.', 'error')
        return redirect(url_for('result', room_id=room_id, is_correct=is_correct))

    # Flag the question as reported in the original database
    if 'reported' not in question_data:
        question_data['reported'] = True
        try:
            question_uploader.update_question(question_id, {'reported': True})
        except Exception:
            # Non-fatal for reporting flow
            pass

    # Report the question
    success, report_id = reported_question_manager.report_question(question_data, reporter=player_name)

    if success:
        admin_setup.record_stat('questions_reported')
        admin_setup.log_event(
            f"Question reported by {player_name or 'a player'} (report {report_id})",
            level='WARNING', category='CONTENT')

    # Best-effort: push the new report record (and the 'reported' flag on the
    # question) to GitHub. Fire-and-forget; never blocks the report flow.
    if success:
        try:
            from contents.admin_controls.github_integration import push_reports_async
            push_reports_async(detach=True)
        except Exception as e:
            try:
                current_app.logger.warning(f"GitHub auto-push after report skipped: {e}")
            except Exception:
                pass

    message = 'Question reported successfully. Thank you for your feedback!' if success else 'Failed to report question. Please try again.'

    if wants_json:
        status = 200 if success else 500
        return jsonify({'success': success, 'message': message, 'report_id': report_id if success else None}), status

    # Legacy behavior: flash + redirect to result page
    if success:
        flash(message)
    else:
        flash(message, 'error')

    return redirect(url_for('result', room_id=room_id, is_correct=is_correct))

@app.route('/leaderboard/<room_id>')
def leaderboard(room_id):
    """View the leaderboard for a game room."""
    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    game_room = game_rooms[room_id]

    # Get the leaderboard
    leaderboard = []
    if hasattr(game_room, 'question_manager'):
        leaderboard = game_room.question_manager.get_leaderboard(all_players=game_room.players)

    # Determine which template to use based on the room_id
    template = 'Columns/leaderboard.html'

    return render_template(
        template,
        room_id=room_id,
        leaderboard=leaderboard,
        room=game_room
    )

@app.route('/reported_questions')
def reported_questions():
    """View and manage reported questions."""
    # Check if the user is authenticated as an admin
    is_authenticated = session.get('admin_authenticated', False)
    if not is_authenticated:
        return render_template('reported_questions.html', is_authenticated=False)

    # Get the status filter (default to 'pending' only when parameter is missing)
    status = request.args.get('status')
    if status is None:
        status = 'pending'

    # Load reports
    reported_question_manager.load_reports()

    # Get reports, filtered by status if provided, and include question data from the original database
    reports = reported_question_manager.get_all_reports(status, question_uploader)

    return render_template(
        'reported_questions.html',
        is_authenticated=True,
        reports=reports,
        status=status
    )

@app.route('/update_report_status', methods=['POST'])
def update_report_status():
    """Update the status of a reported question."""
    # Check if the user is authenticated as an admin
    is_authenticated = session.get('admin_authenticated', False)
    if not is_authenticated:
        flash('You must be logged in as an admin to perform this action.', 'error')
        return redirect(url_for('reported_questions'))

    report_id = request.form.get('report_id')
    status = request.form.get('status')

    if not report_id or not status:
        flash('Invalid request.', 'error')
        return redirect(url_for('reported_questions'))

    success = reported_question_manager.update_report_status(report_id, status)

    if success:
        flash(f'Report status updated to {status}.')
    else:
        flash('Failed to update report status.', 'error')

    return redirect(url_for('reported_questions'))

@app.route('/edit_reported_question/<report_id>', methods=['GET', 'POST'])
def edit_reported_question(report_id):
    """Edit a reported question using the add question template."""
    # Check if the user is authenticated as an admin
    is_authenticated = session.get('admin_authenticated', False)
    if not is_authenticated:
        flash('You must be logged in as an admin to perform this action.', 'error')
        return redirect(url_for('reported_questions'))

    # Get the report with question data from the original database
    report = reported_question_manager.get_report(report_id, question_uploader)

    if not report:
        flash('Report not found.', 'error')
        return redirect(url_for('reported_questions'))

    # Get the question data from the report
    if 'question_data' not in report:
        flash('Question data not found in the original database.', 'error')
        return redirect(url_for('reported_questions'))

    question = report['question_data']

    if request.method == 'POST':
        question_text = request.form.get('question')
        question_type = request.form.get('type')
        category_id = request.form.get('category_id')
        points = request.form.get('points')
        explanation = request.form.get('explanation')
        action = request.form.get('action', 'save_close')  # Default to save_close if not specified

        # Create question data based on type
        question_data = {
            'type': question_type,
            'question': question_text,
        }

        if question_type == 'multiple_choice':
            options = []
            for i in range(1, 5):
                option = request.form.get(f'option_{i}')
                if option:
                    options.append(option)

            correct_answer = request.form.get('correct_answer')
            question_data['options'] = options
            question_data['correct_answer'] = correct_answer

        elif question_type == 'true_false':
            correct_answer = request.form.get('correct_answer_tf')
            question_data['correct_answer'] = correct_answer

        elif question_type == 'text':
            correct_answer = request.form.get('correct_answer_text')
            question_data['correct_answer'] = correct_answer

        # Preserve the ID and other metadata
        question_data['id'] = question['id']
        question_data['created_at'] = question.get('created_at')
        question_data['updated_at'] = datetime.now().isoformat()
        question_data['category_id'] = category_id
        # Convert points to integer, with error handling
        try:
            question_data['points'] = int(points)
        except (ValueError, TypeError):
            # If conversion fails, keep the original value or set a default
            question_data['points'] = question.get('points', 0)
        question_data['explanation'] = explanation

        # Update the question in the question uploader
        success, message = question_uploader.update_question(question_data['id'], question_data)

        if success:
            # Update the report status
            reported_question_manager.update_report_status(report_id, 'reviewed')

            # Reload question_bank to get the updated questions
            question_bank.load_questions()

            flash('Question updated successfully.')

            # Handle different actions
            if action == 'save_next':
                # Get all reports
                reports = reported_question_manager.get_all_reports()
                if reports:
                    # Find the current report index
                    current_index = -1
                    for i, r in enumerate(reports):
                        if r.get('report_id') == report_id:
                            current_index = i
                            break

                    # Get the next report
                    if current_index >= 0 and current_index < len(reports) - 1:
                        next_report = reports[current_index + 1]
                        return redirect(url_for('edit_reported_question', report_id=next_report.get('report_id')))

            # Default action: save_close
            return redirect(url_for('reported_questions'))
        else:
            flash(f'Failed to update question: {message}','error')

    # Get categories for the template
    categories = get_categories_with_questions()

    # Modify the form action to point to the edit_reported_question route
    form_action = url_for('edit_reported_question', report_id=report_id)

    # Create a response with the template
    response = make_response(render_template(
        'add_question.html',
        categories=categories,
        question=question,
        editing=True,
        form_action=form_action
    ))

    # Add a script to modify the page after it loads
    script = f"""
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            // Change the form action - ensure this happens even if the page structure changes
            var forms = document.querySelectorAll('form');
            forms.forEach(function(form) {{
                if (form.classList.contains('form-group-xx')) {{
                    form.action = '{form_action}';
                }}
            }});

            // Find the back button
            var backButton = document.querySelector('.actions a.button');
            if (backButton) {{
                // Change the back button to point to the reported questions page
                backButton.href = '{url_for('reported_questions')}';
                backButton.textContent = 'Back to Reported Questions';
            }}

            // Add report information if available
            var actionsDiv = document.querySelector('.actions');
            if (actionsDiv) {{
                var reportInfo = document.createElement('div');
                reportInfo.className = 'text-clear';
                reportInfo.innerHTML = `
                    <h3>Report Information</h3>
                    <small><strong>Report ID:</strong> {report['report_id']}</small>
                    <small><strong>Question ID:</strong> {report['question_id']}</small>
                    <small><strong>Reported By:</strong> {report['reporter'] or 'Anonymous'}</small>
                    <small><strong>Reported At:</strong> {report['reported_at']}</small>
                    <p><strong>Status:</strong> <span class="status-badge status-{report['status']}">{report['status']}</span></p>
                `;
                actionsDiv.parentNode.insertBefore(reportInfo, actionsDiv.nextSibling);

                // Add styles for the report info
                var style = document.createElement('style');
                style.textContent = `
                    .report-info {{
                        margin-bottom: 20px;
                        padding: 15px;
                        background-color: #f8f9fa;
                        border-radius: 5px;
                        border-left: 4px solid #007bff;
                    }}

                    .report-info p {{
                        margin: 5px 0;
                    }}

                    .status-badge {{
                        padding: 5px 10px;
                        border-radius: 20px;
                        font-size: 0.8em;
                        font-weight: bold;
                    }}

                    .status-pending {{
                        background-color: #ffc107;
                        color: #000;
                    }}

                    .status-reviewed {{
                        background-color: #28a745;
                        color: #fff;
                    }}

                    .status-rejected {{
                        background-color: #dc3545;
                        color: #fff;
                    }}
                `;
                document.head.appendChild(style);
            }}
        }});
    </script>
    """

    # Inject the script at the end of the body
    response_html = response.get_data(as_text=True)
    response_html = response_html.replace('</body>', script + '</body>')
    response.set_data(response_html)

    return response

@app.route('/reset_game', methods=['POST'])
def reset_game():
    """Redirect to the create-room page to start a new game."""
    room_id = request.form.get('room_id')
    player_name = session.get('player_name')

    if not room_id or not player_name:
        flash('Please join a game first.', 'error')
        return redirect(url_for('index'))

    if room_id not in game_rooms:
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    game_room = game_rooms[room_id]

    # Check if the player is the host
    if not game_room.is_host(player_name):
        flash('Only the host can start a new game.', 'error')
        return redirect(url_for('game_room', room_id=room_id))

    # End the current game if one exists
    if game_room.current_game:
        game_room.end_game()

        # Add a game event for the game ending
        add_game_event(room_id, 'game_ended', {
            'player_name': player_name,
            'message': f'The game has been ended by the host ({player_name}) to start a new game'
        })

        # Sync all changed app data to GitHub (see end_game).
        _request_github_sync(f"game reset ({room_id})")

    # Redirect to the create-room page
    flash('Starting a new game...')
    return redirect(url_for('create_room'))

@app.route('/notify_game_room', methods=['GET', 'POST'])
def notify_game_room():
    """Endpoint the game pages poll every second (and ping after using a tool).

    Board changes reach the pages through /api/game_updates, so no forced
    reload is ever needed; answering here stops the per-second 404s.
    """
    return jsonify({'refresh': False})


@app.route('/use_tool', methods=['POST'])
def use_tool():
    """Use a player tool."""
    room_id = session.get('room_id')
    player_name = session.get('player_name')

    # Check if request is AJAX (fetch)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'

    if not room_id or not player_name:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please join a game first.'})
        flash('Please join a game first.', 'error')
        return redirect(url_for('index'))

    if room_id not in game_rooms:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Game room not found.'})
        flash('Game room not found.', 'error')
        return redirect(url_for('index'))

    game_room = game_rooms[room_id]

    tool_name = request.form.get('tool_name')

    # Use the utility function to process the tool request
    from contents.game_tools.gametoolsutil import process_tool_request
    return process_tool_request(tool_name, session, game_room, is_ajax, room_id, player_name, question_uploader)

def get_categories_with_questions():
    """
    Get all categories that have at least one question.

    As per PRJ-003 rule, categories are dynamically derived from questions in the database.
    No categories are stored in the system with no questions.
    """
    # Get categories directly from question_bank
    categories_with_questions = {}

    # Ensure question_bank has the latest data
    question_bank.load_questions()

    # Iterate through categories in question_bank
    for category_id, question_ids in question_bank.categories.items():
        if question_ids:  # Only include categories with at least one question
            # Check if category exists in category_manager
            category = category_manager.get_category(category_id)

            # If category doesn't exist in category_manager, create it
            if not category:
                # Create a default name from the category_id
                name = category_id.replace('_', ' ').title()
                category_manager.add_category(category_id, name)
                category = category_manager.get_category(category_id)

            # Update question count
            category['question_count'] = len(question_ids)
            categories_with_questions[category_id] = category

    return categories_with_questions

@app.route('/question_bank')
def question_bank_page():
    """View and manage the question bank."""
    # Reload questions from disk to ensure we have the latest data
    question_bank.load_questions()

    # Remove any duplicate questions
    question_uploader.load_questions()
    question_uploader.remove_duplicate_questions()

    # Get categories with questions
    categories = get_categories_with_questions()

    # Calculate statistics about the question database
    stats = {
        'total_questions': len(question_bank.questions),
        'total_categories': len(categories),
        'points_distribution': {},
        'question_types': {},
        'active_questions': 0,
        'total_uses': 0  # Initialize total uses count
    }

    # Initialize category use counts
    category_use_counts = {}
    for category_id in categories:
        category_use_counts[category_id] = 0

    # Calculate points distribution and question types
    for question_id, question in question_bank.questions.items():
        # Count active questions
        if question.get('active', True):
            stats['active_questions'] += 1

        # Count points distribution
        points = question.get('points', 0)
        # Ensure points is an integer
        if isinstance(points, str):
            try:
                points = int(points)
            except ValueError:
                points = 0
        if points not in stats['points_distribution']:
            stats['points_distribution'][points] = 0
        stats['points_distribution'][points] += 1

        # Count question types
        q_type = question.get('type', 'unknown')
        if q_type not in stats['question_types']:
            stats['question_types'][q_type] = 0
        stats['question_types'][q_type] += 1

        # Add to total uses count
        use_count = question.get('use_count', 0)
        stats['total_uses'] += use_count

        # Add to category use count
        category_id = question.get('category_id')
        if category_id in category_use_counts:
            category_use_counts[category_id] += use_count

    # Calculate usage percentage for each category
    for category_id, category in categories.items():
        if stats['total_uses'] > 0:
            usage_percentage = (category_use_counts[category_id] / stats['total_uses']) * 100
            category['usage_percentage'] = round(usage_percentage, 1)
        else:
            category['usage_percentage'] = 0

    # Sort the points distribution
    stats['points_distribution'] = dict(sorted(stats['points_distribution'].items()))

    return render_template('question_bank.html', categories=categories, stats=stats)

@app.route('/edit_category/<category_id>', methods=['GET', 'POST'])
def edit_category(category_id):
    """Edit a category."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        new_category_id = request.form.get('category_id')

        # Update the category
        update_data = {
            'name': name,
            'description': description
        }

        # Handle category ID change
        if new_category_id != category_id:
            # Create a new category with the new ID
            category = category_manager.get_category(category_id)
            if category:
                # Copy all properties to the new category
                success = category_manager.add_category(
                    new_category_id, 
                    name, 
                    parent_id=category.get('parent_id'),
                    description=description,
                    icon=category.get('icon')
                )

                if success:

                    # Update category_id in all questions that belong to the old category
                    # First load all questions to ensure we have the latest data
                    question_uploader.load_questions()
                    questions = question_uploader.get_questions_by_category(category_id)
                    for question in questions:
                        # Update the category_id in the question
                        question_uploader.update_question(question['id'], {'category_id': new_category_id})

                    # Delete the old category
                    category_manager.delete_category(category_id)

                    # Remove any duplicate questions that might have been created
                    question_uploader.remove_duplicate_questions()

                    # Best-effort auto-push
                    try:
                        from contents.admin_controls.github_integration import push_all_amended_questions_async
                        push_all_amended_questions_async(detach=True)
                    except Exception:
                        pass

                    flash('Category updated successfully with new ID!')
                    return redirect(url_for('question_bank_page'))
                else:
                    flash('Failed to update category ID. ID may already be in use.', 'error')
            else:
                flash('Category not found.', 'error')
                return redirect(url_for('question_bank_page'))
        else:
            # Just update the existing category
            success = category_manager.update_category(category_id, **update_data)

            if success:
                flash('Category updated successfully!')
                # Best-effort auto-push
                try:
                    from contents.admin_controls.github_integration import push_all_amended_questions_async
                    push_all_amended_questions_async(detach=True)
                except Exception:
                    pass
            else:
                flash('Failed to update category.', 'error')

        return redirect(url_for('question_bank_page'))

    # GET request
    category = category_manager.get_category(category_id)
    if not category:
        flash('Category not found.', 'error')
        return redirect(url_for('question_bank_page'))

    return render_template('edit_category.html', category_id=category_id, category=category)

@app.route('/question_bank/view/<category_id>')
def view_questions(category_id):
    """View questions in a specific category."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.')
        return redirect(url_for('admin_controls'))
    # Reload questions from disk to ensure we have the latest data
    question_bank.load_questions()

    # Remove any duplicate questions
    question_uploader.load_questions()
    question_uploader.remove_duplicate_questions()

    # Reload question_bank to get the updated questions
    question_bank.load_questions()

    category = category_manager.get_category(category_id)
    questions = question_bank.get_questions_by_category(category_id)

    # Calculate category statistics
    stats = {
        'total_questions': len(questions),
        'total_usage': sum(q.get('use_count', 0) for q in questions),
        'by_type': {},
        'by_points': {}
    }

    # Count questions by type and points
    for question in questions:
        q_type = question.get('type', 'unknown')
        points = question.get('points', 0)

        # Count by type
        if q_type not in stats['by_type']:
            stats['by_type'][q_type] = 0
        stats['by_type'][q_type] += 1

        # Count by points
        if points not in stats['by_points']:
            stats['by_points'][points] = 0
        stats['by_points'][points] += 1

    # Sort the points for display
    stats['points_sorted'] = sorted(stats['by_points'].keys())

    return render_template('view_questions.html', category=category, questions=questions, stats=stats)

@app.route('/question_bank/edit/<question_id>')
def edit_question(question_id):
    """Edit a question."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    # Get the question
    question = question_uploader.get_question(question_id)
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('admin_controls'))

    # Redirect to the add_question_page with the question_id as a parameter
    return redirect(url_for('add_question_page', question_id=question_id))

@app.route('/question_bank/delete/<question_id>')
def delete_question(question_id):
    """Delete a question."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    # Get the question to determine its category
    question = question_uploader.get_question(question_id)
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('admin_controls'))

    category_id = question.get('category_id', 'general')

    # Delete the question
    success = question_uploader.delete_question(question_id)

    if success:
        # Reload question_bank to reflect the changes
        question_bank.load_questions()
        flash('Question deleted successfully.')
        # Best-effort auto-push
        try:
            from contents.admin_controls.github_integration import push_all_amended_questions_async
            push_all_amended_questions_async(detach=True)
        except Exception:
            pass
    else:
        flash('Failed to delete question.', 'error')

    # Redirect back to the view_questions page for the category
    return redirect(url_for('view_questions', category_id=category_id))

@app.route('/question_bank/delete_category_questions/<category_id>')
def delete_category_questions(category_id):
    """Delete all questions in a category."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))

    # Delete all questions in the category
    success, count = question_uploader.delete_questions_by_category(category_id)

    if success:
        # Reload question_bank to reflect the changes
        question_bank.load_questions()
        flash(f'Successfully deleted {count} questions from the category.')
        # Best-effort auto-push
        try:
            from contents.admin_controls.github_integration import push_all_amended_questions_async
            push_all_amended_questions_async(detach=True)
        except Exception:
            pass
    else:
        flash('No questions found in this category or deletion failed.', 'error')

    # Redirect back to the question bank page
    return redirect(url_for('question_bank_page'))

@app.route('/question_bank/add', methods=['GET', 'POST'])
def add_question_page():
    """Add or edit a question in the question bank."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    # Check if we're editing an existing question
    question_id = request.args.get('question_id')
    editing = question_id is not None
    question = None

    if editing:
        # Load the question to edit
        question = question_uploader.get_question(question_id)
        if not question:
            flash('Question not found.', 'error')
            return redirect(url_for('admin_controls'))

    if request.method == 'POST':
        question_text = request.form.get('question')
        question_type = request.form.get('type')
        category_id = request.form.get('category_id')
        points = request.form.get('points')
        # Convert points to integer if it's a string
        if points and isinstance(points, str):
            try:
                points = int(points)
            except ValueError:
                # If conversion fails, keep the original value
                pass
        explanation = request.form.get('explanation')
        action = request.form.get('action', 'save_close')  # Default to save_close if not specified

        # Create question data based on type
        question_data = {
            'type': question_type,
            'question': question_text,
            'explanation': explanation,
        }

        if question_type == 'multiple_choice':
            options = []
            for i in range(1, 5):
                option = request.form.get(f'option_{i}')
                if option:
                    options.append(option)

            correct_answer = request.form.get('correct_answer')
            question_data['options'] = options
            question_data['correct_answer'] = correct_answer

        elif question_type == 'true_false':
            correct_answer = request.form.get('correct_answer_tf')
            question_data['correct_answer'] = correct_answer

        elif question_type == 'text':
            correct_answer = request.form.get('correct_answer_text')
            question_data['correct_answer'] = correct_answer

        if editing:
            # Update the existing question
            # Preserve the ID and other metadata
            question_data['id'] = question_id
            question_data['created_at'] = question.get('created_at')
            question_data['updated_at'] = datetime.now().isoformat()
            question_data['category_id'] = category_id
            question_data['points'] = points

            # Update the question in the question uploader
            question_uploader.update_question(question_id, question_data)

            # Reload question_bank to get the updated questions
            question_bank.load_questions()

            flash('Question updated successfully!')
        else:
            # Add a new question
            # Add the question to the question bank
            question_bank.add_question(question_data, category_id, points)

            # Also add the question to the question uploader to ensure consistency
            question_uploader.add_question(question_data, category_id)

            # Remove any duplicate questions that might have been created
            question_uploader.remove_duplicate_questions()

            # Reload question_bank to get the updated questions
            question_bank.load_questions()

            flash('Question added successfully!')

        # Best-effort auto-push for both add and edit
        try:
            from contents.admin_controls.github_integration import push_all_amended_questions_async
            push_all_amended_questions_async(detach=True)
        except Exception:
            pass

        # Handle different actions
        if action == 'save_next':
            # Get the next question in the category
            questions = question_uploader.get_questions_by_category(category_id)
            if questions:
                # Find the current question index
                current_index = -1
                for i, q in enumerate(questions):
                    if q.get('id') == question_id:
                        current_index = i
                        break

                # Get the next question
                if current_index >= 0 and current_index < len(questions) - 1:
                    next_question = questions[current_index + 1]
                    return redirect(url_for('edit_question', question_id=next_question.get('id')))

        # Default action: save_close
        return redirect(url_for('admin_controls'))

    categories = get_categories_with_questions()
    return render_template('add_question.html', categories=categories, question=question, editing=editing)

@app.route('/bulk_import', methods=['GET', 'POST'])
def bulk_import_page():
    """Import questions in bulk."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)

        if file:
            # Save the uploaded file to a temporary location
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)

            # Get form data
            default_category = request.form.get('default_category', 'general')
            # Always create categories if they don't exist, regardless of checkbox
            create_categories = True

            try:
                # Import the questions
                import_stats = bulk_import.import_from_file(file_path, default_category, create_categories)

                admin_setup.record_stat('bulk_imports')
                admin_setup.record_stat('questions_saved', import_stats.get('successful', 0))
                admin_setup.log_event(
                    f"Bulk import: {import_stats.get('successful', 0)} added, "
                    f"{import_stats.get('failed', 0)} failed",
                    level='SUCCESS' if import_stats.get('successful', 0) else 'WARNING',
                    category='CONTENT')

                # Remove any duplicate questions that might have been created
                num_duplicates = question_uploader.remove_duplicate_questions()
                if num_duplicates > 0:
                    print(f"Removed {num_duplicates} duplicate questions after bulk import")

                # Reload question_bank to get the updated questions
                question_bank.load_questions()

                # Remove the temporary file
                os.remove(file_path)

                # Best-effort auto-push
                try:
                    from contents.admin_controls.github_integration import push_all_amended_questions_async
                    push_all_amended_questions_async(detach=True)
                except Exception:
                    pass

                flash(f'Successfully imported {import_stats["successful"]} questions. Failed: {import_stats["failed"]}')
                return redirect(url_for('admin_controls'))

            except Exception as e:
                flash(f'Error importing questions: {str(e)}', 'error')
                return redirect(request.url)

    categories = get_categories_with_questions()
    return render_template('bulk_import.html', categories=categories)

@app.route('/export_template/<format>')
def export_template_route(format):
    """Export a template for question import."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    if format not in ['csv', 'xlsx']:
        flash('Invalid format. Please choose CSV or XLSX.', 'error')
        return redirect(url_for('bulk_import_page'))

    try:
        # Create a temporary file for the template
        temp_dir = tempfile.gettempdir()
        file_name = f'avirta_template.{format}'
        file_path = os.path.join(temp_dir, file_name)

        # Export the template
        success, message = export_template(file_path, format)

        if success:
            return send_file(file_path, as_attachment=True, download_name=file_name)
        else:
            flash(f'Error exporting template: {message}', 'error')
            return redirect(url_for('bulk_import_page'))

    except Exception as e:
        flash(f'Error exporting template: {str(e)}', 'error')
        return redirect(url_for('bulk_import_page'))

@app.route('/export_questions/<category_id>')
@app.route('/export_questions/<category_id>/<format>')
def export_questions(category_id, format='csv'):
    """Export questions from a specific category."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))

    # Validate format
    if format not in ['csv', 'xlsx', 'json']:
        flash('Invalid format. Please choose CSV, XLSX, or JSON.', 'error')
        return redirect(url_for('admin_controls'))

    try:
        # Create a temporary file for the export
        temp_dir = tempfile.gettempdir()
        file_name = f'avirta_questions_{category_id}.{format}'
        file_path = os.path.join(temp_dir, file_name)

        # Export the questions
        success, message = bulk_import.export_to_file(file_path, category_id)

        if not success:
            flash(f'Error exporting questions: {message}', 'error')
            return redirect(url_for('admin_controls'))

        return send_file(file_path, as_attachment=True, download_name=file_name)

    except Exception as e:
        flash(f'Error exporting questions: {str(e)}', 'error')
        return redirect(url_for('admin_controls'))

@app.route('/ai_question_history')
def ai_question_history():
    """View history of AI-generated questions."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))

    # Get all batches
    batches = get_all_batches()

    return render_template(
        'ai_question_history.html',
        batches=batches,
        admin_setup=admin_setup
    )

@app.route('/ai_question_history/<batch_id>')
def ai_question_history_detail(batch_id):
    """View details of a specific AI-generated question batch."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))

    # Get the batch metadata and questions
    metadata = get_batch_metadata(batch_id)
    if not metadata:
        flash('Batch metadata not found. The batch may have been deleted or corrupted.', 'error')
        return redirect(url_for('ai_question_history'))

    questions = get_batch(batch_id)
    if not questions:
        flash('Questions not found for this batch. The data may have been corrupted or deleted.', 'error')
        return redirect(url_for('ai_question_history'))

    # Get all batches for navigation
    all_batches = get_all_batches()
    batch_ids = [b['batch_id'] for b in all_batches]

    # Find current batch index
    try:
        current_index = batch_ids.index(batch_id)
        prev_batch = batch_ids[current_index + 1] if current_index < len(batch_ids) - 1 else None
        next_batch = batch_ids[current_index - 1] if current_index > 0 else None
    except ValueError:
        current_index = -1
        prev_batch = None
        next_batch = None

    return render_template(
        'ai_question_history_detail.html',
        batch_id=batch_id,
        metadata=metadata,
        questions=questions,
        prev_batch=prev_batch,
        next_batch=next_batch,
        current_index=current_index,
        total_batches=len(all_batches),
        admin_setup=admin_setup
    )

@app.route('/export_questions_xlsx/<category_id>')
def export_questions_xlsx(category_id):
    """Export questions from a specific category to an XLS file."""
    # Check if user is authenticated as admin
    if not session.get('admin_authenticated', False):
        flash('You must be logged in as an admin to access this page.', 'error')
        return redirect(url_for('admin_controls'))
    try:
        # Create a temporary file for the export
        temp_dir = tempfile.gettempdir()
        file_name = f'avirta_questions_{category_id}.xlsx'
        file_path = os.path.join(temp_dir, file_name)

        # Get questions from the category
        question_uploader.load_questions()
        questions = question_uploader.get_questions_by_category(category_id)

        # Check if openpyxl is available
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
        except ImportError:
            flash('openpyxl library is required for Excel export. Please install it with: pip install openpyxl', 'error')
            return redirect(url_for('question_bank_page'))

        # Create a new workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Questions - {category_id}"

        # Determine all possible fields
        fields = set()
        for question in questions:
            fields.update(question.keys())

        # Ensure essential fields come first
        essential_fields = ["id", "question", "type", "category_id", "correct_answer"]
        fieldnames = essential_fields + [f for f in sorted(fields) if f not in essential_fields]

        # Add headers
        for col_num, header in enumerate(fieldnames, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

            # Set column width based on header length
            ws.column_dimensions[get_column_letter(col_num)].width = max(15, len(header) + 5)

        # Add data
        for row_num, question in enumerate(questions, 2):
            for col_num, field in enumerate(fieldnames, 1):
                cell = ws.cell(row=row_num, column=col_num)
                value = question.get(field, "")

                # Handle lists (options)
                if isinstance(value, list):
                    value = ", ".join(value)

                cell.value = value

        # Save the workbook
        wb.save(file_path)

        return send_file(file_path, as_attachment=True, download_name=file_name)

    except Exception as e:
        flash(f'Error exporting questions to Excel: {str(e)}', 'error')
        return redirect(url_for('question_bank_page'))


@app.route('/download_exported_file', methods=['GET'])
def download_exported_file():
    """Download the exported file stored in the session."""
    file_path = session.get('download_file')
    file_name = session.get('download_filename')

    if not file_path or not file_name or not os.path.exists(file_path):
        flash('No file available for download or file has expired.', 'error')
        return redirect(url_for('admin_controls'))

    # Clear the session variables
    session.pop('download_file', None)
    session.pop('download_filename', None)

    return send_file(file_path, as_attachment=True, download_name=file_name)

@app.route('/admin', methods=['GET', 'POST'])
def admin_controls():
    """Admin controls page with authentication."""
    # Check if user is already authenticated
    is_authenticated = session.get('admin_authenticated', False)
    login_error = None

    if request.method == 'POST':
        action = request.form.get('action')

        # Handle logout
        if action == 'logout':
            session['admin_authenticated'] = False
            flash('You have been logged out.')
            return redirect(url_for('index'))

        # Handle general settings update
        elif action == 'update_settings' and is_authenticated:
            for setting_name in admin_setup.game_settings.keys():
                if setting_name in request.form:
                    value = request.form.get(setting_name)

                    # Convert string values to appropriate types
                    if value.lower() == 'true':
                        value = True
                    elif value.lower() == 'false':
                        value = False
                    elif value.isdigit():
                        value = int(value)

                        # Validate max_categories_per_room is within range 3-7
                        if setting_name == 'max_categories_per_room':
                            value = max(3, min(7, value))  # Ensure value is between 3 and 7

                    admin_setup.update_game_setting(setting_name, value)

            flash('Game settings updated successfully.')

        # Handle login
        else:
            username = request.form.get('username')
            password = request.form.get('password')

            # Check credentials against the hash in Secret Manager (see
            # contents/admin_controls/admin_auth.py); repeated failures lock out.
            from contents.admin_controls import admin_auth
            login_ok, login_message = admin_auth.check_login(
                admin_auth.client_key(request), username, password)
            if login_ok:
                session['admin_authenticated'] = True
                admin_setup.record_stat('logins')
                admin_setup.log_event("Admin user logged in", level='SUCCESS', category='AUTH')
                flash('Login successful.')
                return redirect(url_for('admin_controls'))
            else:
                login_error = login_message
                is_authenticated = False
                admin_setup.record_stat('failed_logins')
                admin_setup.log_event(f"Failed admin login attempt for username '{username}'",
                                      level='WARNING', category='AUTH')

    return render_template(
        'admin_controls.html',
        is_authenticated=is_authenticated,
        login_error=login_error,
        admin_setup=admin_setup,
        system_stats=admin_setup.get_stats(),
    )




@app.route('/admin/git_push', methods=['POST'])
def admin_git_push():
    """Admin "Sync to GitHub": send every changed data file in one commit."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1' or request.is_json
    if not session.get('admin_authenticated', False):
        if is_ajax:
            return jsonify({"success": False, "message": "You must be logged in as an admin."}), 403
        flash('You must be logged in as an admin to perform this action.', 'error')
        return redirect(url_for('admin_controls'))
    ok, msg = _request_github_sync("manual sync")
    admin_setup.record_stat('github_question_pushes')
    if is_ajax:
        return jsonify({"success": ok, "message": msg})
    flash(msg)
    return redirect(url_for('admin_controls'))


@app.route('/admin/git_push_status', methods=['GET'])
def admin_git_push_status():
    """Get the current progress of the git push operation.
    
    Admin-only. Returns JSON containing progress details.
    """
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Unauthorized"}), 403
    
    from contents.admin_controls.github_integration import get_push_progress
    return jsonify(get_push_progress())


# --- GitHub sync failure pop-up (admins, and hosts who just ended a game) -----
_SYNC_WATCH_SECONDS = 15 * 60


def _sync_alert_audience():
    """True when this browser should be told about sync failures."""
    if session.get('admin_authenticated', False):
        return True
    watch = session.get('sync_watch')
    return bool(watch) and (time.time() - float(watch)) < _SYNC_WATCH_SECONDS


@app.context_processor
def _inject_sync_alert_flag():
    return {'show_sync_alerts': _sync_alert_audience()}


@app.route('/api/sync/alerts', methods=['GET'])
def sync_alerts():
    """Current GitHub sync state for the pop-up poller."""
    if not _sync_alert_audience():
        session.pop('sync_watch', None)
        return jsonify({"watch": False})
    from contents.admin_controls.github_sync import current_failure, get_status
    st = get_status()
    failure = current_failure()
    if failure and failure.get('id') == session.get('sync_ack'):
        failure = None
    busy = st['status'] == 'running' or bool(st['pending'])
    if not busy and not failure and not session.get('admin_authenticated') and st.get('last_success'):
        # A host's sync finished fine: stop watching.
        session.pop('sync_watch', None)
    return jsonify({
        "watch": True,
        "busy": busy,
        "failure": failure,
        "is_admin": bool(session.get('admin_authenticated')),
        "last_success": st.get('last_success'),
    })


@app.route('/api/sync/ack', methods=['POST'])
def sync_ack():
    data = request.get_json(silent=True) or {}
    session['sync_ack'] = str(data.get('id') or '')[:20]
    return jsonify({"ok": True})


@app.route('/api/sync/retry', methods=['POST'])
def sync_retry():
    if not session.get('admin_authenticated', False):
        return jsonify({"ok": False, "message": "Admins only."}), 403
    ok, msg = _request_github_sync("retry after failure")
    return jsonify({"ok": ok, "message": msg})


@app.route('/get_game_state/<room_id>')
def get_game_state(room_id):
    """
    Get the current game state for a room.
    This endpoint is used by the legacy JavaScript in joined_room.html.
    It redirects to the new /api/game_updates endpoint.
    """
    return redirect(url_for('game_updates', room_id=room_id))

@app.route('/_ah/health')
def health_check():
    """
    Health check endpoint for App Engine.
    This endpoint is used by App Engine to determine if the application is healthy.
    """
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/get-json')
def get_json():
    """
    Get data from data.json file as a JSON response.
    This endpoint reads the data.json file and returns its contents.
    """
    try:
        # Use a configurable path or relative to application root
        file_path = current_app.config.get('DATA_JSON_PATH', 'data.json')
        with open(file_path, 'r') as file:
            data = json.load(file)
        return jsonify(data)
    except FileNotFoundError as e:
        current_app.logger.error(f"File not found: {e}")
        return jsonify({"error": "File not found"}), 404
    except json.JSONDecodeError as e:
        current_app.logger.error(f"JSON decode error: {e}")
        return jsonify({"error": "Invalid JSON format"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500


register_ai_routes(
    app,
    admin_setup=admin_setup,
    question_bank=question_bank,
    category_manager=category_manager,
    question_uploader=question_uploader,
    get_categories=get_categories_with_questions,
)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
