"""
The Hive (Hex) game routes and entry point module.

This module encapsulates all Flask route handlers and logic solely related to
The Hive game so that app.py stays lean. It defines a function to register
routes on a given Flask app instance using shared state provided by app.py.
"""
from __future__ import annotations

from flask import render_template, request, redirect, url_for, session, flash, jsonify

# Import game room class local to the Hive game
from contents.thehive.hex_game_room import HexGameRoom


def register_hive_routes(app, game_rooms, game_status_manager, question_uploader, add_game_event):
    """Register The Hive (Hex) game routes on the given Flask app.

    Args:
        app (Flask): The Flask application instance.
        game_rooms (dict): Shared dict of room_id -> game room instance.
        game_status_manager: Persistence and events manager with load/persist APIs.
        question_uploader: QuestionUploader instance for fetching questions.
        add_game_event (callable): Function to append a game event.
    """

    @app.route('/hex/create_room', methods=['GET', 'POST'])
    def hex_create_room():
        if request.method == 'POST':
            # Extract form data
            room_id = request.form.get('room_id', '').strip() or None
            room_name = request.form.get('room_name', '').strip()
            team_a = request.form.get('team_a', 'Team A').strip() or 'Team A'
            team_b = request.form.get('team_b', 'Team B').strip() or 'Team B'

            # Point values: from multi-select checkboxes or comma-separated input
            point_values = []
            pv_list = request.form.getlist('point_values')
            if pv_list:
                try:
                    point_values = [int(x) for x in pv_list if str(x).strip()]
                except Exception:
                    point_values = []
            else:
                # Fallback to a single text field with comma/space separated values
                point_values_raw = request.form.get('point_values', '')
                if point_values_raw:
                    try:
                        cleaned = point_values_raw.replace(' ', ',')
                        point_values = [int(x) for x in cleaned.split(',') if x.strip()]
                    except Exception:
                        point_values = []

            # Create a new room id if not supplied
            import uuid
            if not room_id:
                room_id = str(uuid.uuid4())[:8]

            # Determine room display name
            display_name = room_name or f"{team_a} vs {team_b}"

            # Create the Hex game room (expects team_b and no unsupported kwargs)
            hex_room = HexGameRoom(room_id, display_name, team_a, team_b, point_values=point_values)

            # Create the board; if not enough questions, show details
            success, enough_questions, error_details = hex_room.create_board(question_uploader)
            if not success:
                flash('Failed to create Hive game board. Please try different settings.', 'error')
                return redirect(url_for('index'))

            # Store in-memory and persist
            game_rooms[room_id] = hex_room
            try:
                game_status_manager.persist_game_room(room_id, hex_room)
            except Exception:
                pass

            # Default session context: host is team_a
            session['room_id'] = room_id
            session['player_name'] = team_a

            add_game_event(room_id, 'game_started', {
                'message': f'The Hive game started: {team_a} vs {team_b}',
                'teams': [team_a, team_b],
                'point_values': point_values,
            })

            return redirect(url_for('hex_play', room_id=room_id))

        # GET: Provide default point choices
        default_points = [100, 200, 300, 400, 500]
        return render_template('thehive/create_room.html', default_points=default_points)

    @app.route('/hex/play/<room_id>')
    def hex_play(room_id):
        if room_id not in game_rooms:
            loaded = game_status_manager.load_game_room(room_id)
            if not loaded:
                flash('Room not found', 'error')
                return redirect(url_for('index'))
            game_rooms[room_id] = loaded
        hex_room = game_rooms[room_id]
        return render_template('thehive/play.html', room=hex_room.to_dict())

    @app.route('/hex/select_cell', methods=['POST'])
    def hex_select_cell():
        room_id = request.form.get('room_id')
        cell_index = int(request.form.get('cell_index', -1))
        if room_id not in game_rooms:
            return jsonify({'success': False, 'message': 'Room not found'}), 404
        hex_room = game_rooms[room_id]
        result = hex_room.select_cell(cell_index, question_uploader)
        if result.get('success'):
            add_game_event(room_id, 'question_selected', {
                'cell_index': cell_index,
                'points': result['cell']['points']
            })
        game_status_manager.persist_game_room(room_id, hex_room)
        return jsonify(result)

    @app.route('/hex/answer', methods=['POST'])
    def hex_answer():
        room_id = request.form.get('room_id')
        team_name = request.form.get('team_name')
        answer = request.form.get('answer')
        if room_id not in game_rooms:
            return jsonify({'success': False, 'message': 'Room not found'}), 404
        hex_room = game_rooms[room_id]
        res = hex_room.submit_answer(team_name, answer)
        if res.get('success'):
            evt = 'answer_correct' if res.get('correct') else 'answer_incorrect'
            add_game_event(room_id, evt, {
                'team': team_name,
                'cell_index': res['cell']['id'] if res.get('cell') else None,
                'points': res['cell']['points'] if res.get('cell') else None
            })
            if res.get('winner'):
                add_game_event(room_id, 'game_won', {
                    'team': res['winner']['team'],
                    'path': res['winner']['path'],
                    'message': f"{res['winner']['team']} connected their edges and won the game",
                })
        game_status_manager.persist_game_room(room_id, hex_room)
        return jsonify(res)

    @app.route('/hex/game_updates/<room_id>')
    def hex_game_updates(room_id):
        if room_id not in game_rooms:
            loaded = game_status_manager.load_game_room(room_id)
            if not loaded:
                return jsonify({'error': 'Room not found'}), 404
            game_rooms[room_id] = loaded
        hex_room = game_rooms[room_id]
        events = game_status_manager.get_events(room_id)
        data = hex_room.get_board_state()
        data['events'] = events
        return jsonify(data)

    # Return app for convenience/chaining
    return app
