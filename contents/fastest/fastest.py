"""
Fastest (Who is the fastest) game routes and entry point module.

This module encapsulates all Flask route handlers and logic solely related to
The Fastest game so that app.py stays lean. It defines a function to register
routes on a given Flask app instance using shared state provided by app.py.
"""
from __future__ import annotations

from flask import render_template, request, redirect, url_for, session, flash, jsonify

# Import game room class local to the Fastest game
from contents.fastest.fastest_game_room import FastestGameRoom


def register_fastest_routes(app, game_rooms, game_status_manager, question_uploader, add_game_event, admin_setup):
    """Register the Fastest game routes on the given Flask app.

    Args:
        app (Flask): The Flask application instance.
        game_rooms (dict): Shared dict of room_id -> game room instance.
        game_status_manager: Persistence and events manager with load/persist APIs.
        question_uploader: QuestionUploader instance for fetching questions.
        add_game_event (callable): Function to append a game event.
        admin_setup: AdminSetup instance to read game settings (max players, etc.).
    """

    @app.route('/fastest/create_room', methods=['GET', 'POST'])
    def fastest_create_room():
        """Create a new 'Who is the fastest' game room."""
        if request.method == 'POST':
            room_name = request.form.get('room_name')
            host_name = request.form.get('host_name')
            selected_categories = request.form.getlist('categories')
            additional_players = request.form.getlist('additional_players')
            selected_point_values = request.form.getlist('point_values')
            selected_question_types = request.form.getlist('question_types')

            # Convert point values to integers and sort in descending order
            point_values = sorted([int(pv) for pv in selected_point_values], reverse=True)

            if not room_name or not host_name or not selected_categories or not point_values or not selected_question_types:
                session['error_modal'] = 'Please fill in all fields, select at least one category, at least one point value, and at least one question type.'
                return redirect(url_for('fastest_create_room'))

            # Limit to max_categories_per_room (default is 7)
            max_categories = admin_setup.game_settings.get('max_categories_per_room', 7)
            selected_categories = selected_categories[:max_categories]

            # Create a unique room ID
            import uuid
            room_id = f"fastest_{uuid.uuid4().hex[:8]}"

            # Create the Fastest game room with custom point values and question types
            game_room = FastestGameRoom(
                room_id,
                room_name,
                host_name,
                selected_categories,
                max_players=admin_setup.game_settings.get('max_players_per_room', 10),
                point_values=point_values,
                question_types=selected_question_types,
            )

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

            # Create the game board with custom point values and configurable number of questions per category
            questions_per_category = admin_setup.game_settings.get('questions_per_category', 10)
            success, enough_questions, error_details = game_room.create_board(question_uploader, questions_per_category)

            # Check if there were enough questions that matched the criteria
            if not enough_questions:
                # Use detailed error message from the sophisticated algorithm
                detailed_message = error_details.get('overall_message', 'Couldn\'t find enough questions of the selected criteria.')
                # Convert newlines to HTML breaks for proper display in modal
                detailed_message_html = detailed_message.replace('\n', '<br>')
                session['error_modal'] = detailed_message_html
                return redirect(url_for('fastest_create_room'))

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
                'message': f"Who is the fastest game started by {host_name}",
                'categories': selected_categories,
                'point_values': point_values,
                'question_types': selected_question_types,
                'players': game_room.players,
            })

            # Get the first question
            game_room.get_next_question()

            return redirect(url_for('fastest_play', room_id=room_id))

        # GET request
        categories = get_categories_with_questions()
        # Get the maximum number of players per room from admin settings
        max_players = admin_setup.game_settings.get('max_players_per_room', 10)
        # Get the maximum number of categories per room from admin settings
        max_categories = admin_setup.game_settings.get('max_categories_per_room', 7)
        # "Play again" links pre-fill the same players: ?host=Name&players=A,B,C
        prefill_host = (request.args.get('host') or '').strip()
        prefill_players = [p.strip() for p in (request.args.get('players') or '').split(',') if p.strip()]
        # Filter tags for the category picker (contents/category_tags.json).
        from questionmanagement.category_tags import category_tag_filters
        tag_groups, category_tags = category_tag_filters(list(categories))
        return render_template('Fastest/create_room.html', categories=categories, max_players=max_players,
                               max_categories=max_categories, prefill_host=prefill_host,
                               prefill_players=prefill_players,
                               tag_groups=tag_groups, category_tags=category_tags)

    def get_categories_with_questions():
        """Helper: derive categories dynamically from loaded questions (dict of id -> info).
        Returns a dict so templates can do categories.items().
        """
        # Ensure questions are loaded
        try:
            question_uploader.load_questions()
        except Exception:
            pass

        categories = {}
        try:
            for q in getattr(question_uploader, 'questions', {}).values():
                cid = q.get('category_id', 'general')
                if cid not in categories:
                    categories[cid] = {
                        'name': cid.replace('_', ' ').title(),
                        'description': f"Questions about {cid.replace('_', ' ').title()}",
                        'question_count': 0,
                        'active': True,
                    }
                categories[cid]['question_count'] += 1
            return categories
        except Exception:
            # Safe fallback: return empty dict to avoid Jinja .items() error
            return {}

    @app.route('/fastest/play/<room_id>')
    def fastest_play(room_id):
        """Play the 'Who is the fastest' game."""
        # Check if the room exists
        if room_id not in game_rooms:
            # Try to load it from persistence
            game_room = game_status_manager.load_game_room(room_id)
            if game_room:
                # Add it to the in-memory dictionary
                game_rooms[room_id] = game_room
            else:
                session['error_modal'] = 'Game room not found.'
                return redirect(url_for('index'))

        # Get the game room
        game_room = game_rooms[room_id]

        # Check if the player is in the room
        player_name = session.get('player_name')
        if not player_name or player_name not in game_room.players:
            session['error_modal'] = 'You are not a player in this room.'
            return redirect(url_for('index'))

        # Check if the player is the host
        is_host = player_name == game_room.host

        # Get the current question and game stats
        current_question = game_room.current_question
        stats = game_room.get_game_stats()

        # Render the play template
        return render_template('Fastest/play.html',
                              room=game_room,
                              player_name=player_name,
                              is_host=is_host,
                              current_question=current_question,
                              stats=stats)

    @app.route('/fastest/reveal_question', methods=['POST'])
    def fastest_reveal_question():
        """Reveal the current question and start the timer."""
        room_id = request.form.get('room_id')

        # Check if the room exists
        if room_id not in game_rooms:
            flash('Game room not found.', 'error')
            return redirect(url_for('index'))

        # Get the game room
        game_room = game_rooms[room_id]

        # Check if the player is the host
        player_name = session.get('player_name')
        if not player_name or player_name != game_room.host:
            flash('Only the host can reveal questions.', 'error')
            return redirect(url_for('fastest_play', room_id=room_id))

        # Reveal the question
        game_room.reveal_question()

        # Add a game event for the question being revealed
        add_game_event(room_id, 'question_revealed', {
            'player_name': player_name,
            'message': f'Question revealed by {player_name}',
            'question_number': game_room.current_question_number,
            'total_questions': game_room.total_questions,
        })

        # Persist the game room to disk
        game_status_manager.persist_game_room(room_id, game_room)

        return redirect(url_for('fastest_play', room_id=room_id))

    @app.route('/fastest/reveal_answer', methods=['POST'])
    def fastest_reveal_answer():
        """Reveal the answer to the current question."""
        room_id = request.form.get('room_id')

        # Check if the room exists
        if room_id not in game_rooms:
            flash('Game room not found.', 'error')
            return redirect(url_for('index'))

        # Get the game room
        game_room = game_rooms[room_id]

        # Check if the player is the host
        player_name = session.get('player_name')
        if not player_name or player_name != game_room.host:
            flash('Only the host can reveal answers.', 'error')
            return redirect(url_for('fastest_play', room_id=room_id))

        # Reveal the answer
        game_room.reveal_answer()

        # Add a game event for the answer being revealed
        add_game_event(room_id, 'answer_revealed', {
            'player_name': player_name,
            'message': f'Answer revealed by {player_name}',
            'question_number': game_room.current_question_number,
            'total_questions': game_room.total_questions,
        })

        # Persist the game room to disk
        game_status_manager.persist_game_room(room_id, game_room)

        return redirect(url_for('fastest_play', room_id=room_id))

    @app.route('/fastest/award_points', methods=['POST'])
    def fastest_award_points():
        """Award points to a player for answering correctly."""
        room_id = request.form.get('room_id')
        player_name = request.form.get('player_name')

        # Check if the room exists
        if room_id not in game_rooms:
            flash('Game room not found.', 'error')
            return redirect(url_for('index'))

        # Get the game room
        game_room = game_rooms[room_id]

        # Check if the current player is the host
        current_player = session.get('player_name')
        if not current_player or current_player != game_room.host:
            flash('Only the host can award points.', 'error')
            return redirect(url_for('fastest_play', room_id=room_id))

        # Award points to the player
        points = game_room.current_question.get('points', 0)
        game_room.award_points_to_player(player_name)

        # Add a game event for the points being awarded
        add_game_event(room_id, 'points_awarded', {
            'player_name': player_name,
            'message': f'{player_name} answered correctly and earned {points} points',
            'points': points,
            'question_number': game_room.current_question_number,
            'total_questions': game_room.total_questions,
        })

        # Persist the game room to disk
        game_status_manager.persist_game_room(room_id, game_room)

        return redirect(url_for('fastest_leaderboard', room_id=room_id))

    @app.route('/fastest/next_question', methods=['POST'])
    def fastest_next_question():
        """Move to the next question."""
        room_id = request.form.get('room_id')

        # Check if the room exists
        if room_id not in game_rooms:
            flash('Game room not found.', 'error')
            return redirect(url_for('index'))

        # Get the game room
        game_room = game_rooms[room_id]

        # Check if the player is the host
        player_name = session.get('player_name')
        if not player_name or player_name != game_room.host:
            flash('Only the host can move to the next question.', 'error')
            return redirect(url_for('fastest_play', room_id=room_id))

        # Prevent advancing if the board is already completed (server-side safety)
        if game_room.is_board_completed():
            flash('Game Over! All questions have been answered.')
            return redirect(url_for('fastest_leaderboard', room_id=room_id))

        # Get the next question
        next_question = game_room.get_next_question()

        # Check if there are no more questions
        if not next_question:
            flash('Game Over! All questions have been answered.')
            return redirect(url_for('fastest_leaderboard', room_id=room_id))

        # Add a game event for moving to the next question
        add_game_event(room_id, 'next_question', {
            'player_name': player_name,
            'message': f'Moving to question {game_room.current_question_number} of {game_room.total_questions}',
            'question_number': game_room.current_question_number,
            'total_questions': game_room.total_questions,
        })

        # Persist the game room to disk
        game_status_manager.persist_game_room(room_id, game_room)

        return redirect(url_for('fastest_play', room_id=room_id))

    @app.route('/fastest/leaderboard/<room_id>')
    def fastest_leaderboard(room_id):
        """Display the leaderboard for the 'Who is the fastest' game."""
        # Check if the room exists
        if room_id not in game_rooms:
            # Try to load it from persistence
            game_room = game_status_manager.load_game_room(room_id)
            if game_room:
                # Add it to the in-memory dictionary
                game_rooms[room_id] = game_room
            else:
                flash('Game room not found.', 'error')
                return redirect(url_for('index'))

        # Get the game room
        game_room = game_rooms[room_id]

        # Check if the player is in the room
        player_name = session.get('player_name')
        if not player_name or player_name not in game_room.players:
            flash('You are not a player in this room.', 'error')
            return redirect(url_for('index'))

        # Check if the player is the host
        is_host = player_name == game_room.host

        # Get the leaderboard
        leaderboard = game_room.get_leaderboard()

        # Render the leaderboard template
        return render_template('Fastest/leaderboard.html',
                              room=game_room,
                              room_id=room_id,
                              player_name=player_name,
                              is_host=is_host,
                              leaderboard=leaderboard)

    @app.route('/api/fastest_game_updates/<room_id>')
    def fastest_game_updates(room_id):
        """Get updates for the 'Who is the fastest' game."""
        # Check if the room exists
        if room_id not in game_rooms:
            return jsonify({'error': 'Game room not found'})

        # Get the game room
        game_room = game_rooms[room_id]

        # Get the game stats
        stats = game_room.get_game_stats()

        # Get the events for this room
        events = game_status_manager.get_events(room_id)

        # Return the updates
        return jsonify({
            'refresh': False,  # Don't refresh the page by default
            'question_revealed': stats['question_revealed'],
            'answer_revealed': stats['answer_revealed'],
            'current_question_number': stats['current_question_number'],
            'total_questions': stats['total_questions'],
            'current_question': stats['current_question'],
            'events': events  # Include events for status updates
        })

    @app.route('/api/fastest/category_availability')
    def fastest_category_availability():
        """Return per-category availability given selected filters.

        Query params:
          - point_values: comma-separated list of integers (e.g., "100,200,300")
          - question_types: comma-separated list of strings (e.g., "text,multiple_choice")

        Response JSON:
          {
            "required_per_category": 10,
            "categories": {
              "science": {"count": 7, "enough": false},
              ...
            }
          }
        """
        # Parse query params
        pv_raw = request.args.get('point_values', '')
        qt_raw = request.args.get('question_types', '')
        try:
            selected_points = sorted({int(x) for x in pv_raw.split(',') if x.strip()}, reverse=True)
        except Exception:
            selected_points = []
        selected_types = {x.strip() for x in qt_raw.split(',') if x.strip()}

        # Ensure questions are loaded
        try:
            question_uploader.load_questions()
        except Exception:
            pass

        # Determine requirement per category from admin settings
        required = admin_setup.game_settings.get('questions_per_category', 10)

        # Count matching questions per category
        counts = {}
        for q in getattr(question_uploader, 'questions', {}).values():
            # Only active questions
            if not q.get('active', True):
                continue
            # Filter by type
            if selected_types and q.get('type') not in selected_types:
                continue
            # Filter by points
            if selected_points:
                try:
                    q_points = int(q.get('points', 0))
                except Exception:
                    q_points = 0
                if q_points not in selected_points:
                    continue
            cid = q.get('category_id', 'general')
            counts[cid] = counts.get(cid, 0) + 1

        result = {cid: {"count": count, "enough": count >= required} for cid, count in counts.items()}

        # Also include categories with zero matches that exist in uploader
        # so the UI can disable them explicitly
        for q in getattr(question_uploader, 'questions', {}).values():
            cid = q.get('category_id', 'general')
            if cid not in result:
                result[cid] = {"count": 0, "enough": False}

        return jsonify({
            'required_per_category': required,
            'categories': result
        })

    # Return app for convenience/chaining
    return app
