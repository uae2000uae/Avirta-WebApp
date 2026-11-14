"""
Game Tools Utility Module for Avirta

This module provides utility functions for handling game tools in the web application,
bridging between the HTTP layer and the core game tools functionality.

It includes functions for:
- Processing tool usage requests
- Handling tool-specific HTTP responses
- Managing session state for tools
"""

from flask import jsonify, redirect, url_for, flash
from contents.game_room.game_status_manager import add_game_event

def handle_error(is_ajax, message, redirect_url=None):
    """
    Handle error responses for both AJAX and regular requests.

    Args:
        is_ajax (bool): Whether the request is an AJAX request
        message (str): The error message to display
        redirect_url (str, optional): The URL to redirect to for non-AJAX requests

    Returns:
        Response: A JSON response for AJAX requests, or a redirect for regular requests
    """
    if is_ajax:
        return jsonify({'success': False, 'message': message})

    flash(message, 'error')

    return redirect(redirect_url) if redirect_url else None

def process_change_question(tool_name, session, game_room, is_ajax, room_id, player_name, question_uploader, acting_player=None):
    """
    Process a request to change a question.

    Args:
        tool_name (str): The name of the tool being used
        session (dict): The session object
        game_room (GameRoom): The game room object
        is_ajax (bool): Whether the request is an AJAX request
        room_id (str): The ID of the room
        player_name (str): The name of the player
        question_uploader (QuestionUploader): The question uploader object
        acting_player (str, optional): The player on whose behalf the action is being taken

    Returns:
        Response: A response object if the tool was used, None otherwise
    """
    if tool_name != 'change_question':
        return None

    question = session.get('current_question')

    if not question:
        return handle_error(is_ajax, 'No question selected.', url_for('game_room', room_id=room_id))

    category_id, points = question.get('category_id'), question.get('points')

    # Determine the effective player (who will be credited with the action)
    effective_player = player_name

    # If acting_player is provided and player_name is the host, use acting_player
    if acting_player and game_room.is_host(player_name) and acting_player in game_room.players:
        effective_player = acting_player

    result = game_room.use_change_question(player_name, category_id, points, question_uploader, acting_player)

    # Check if result is a successful question (dict without 'success' key or with success=True)
    if result and (not isinstance(result, dict) or result.get('success', True)):
        session['current_question'] = result

        message = 'Question changed successfully!'

        # Customize message if host is acting on behalf of another player
        if game_room.is_host(player_name) and effective_player != player_name:
            message = f'Question changed successfully on behalf of {effective_player}!'

        add_game_event(room_id, 'tool_used', {
            'player_name': player_name,
            'tool_name': 'change_question',
            'category': category_id,
            'points': points,
            'target_player': effective_player if effective_player != player_name else None,
            'message': f'{player_name} used Change Question for {effective_player}' if effective_player != player_name else f'{player_name} used Change Question to get a new question'
        })

        return jsonify({'success': True, 'message': message,
                        'redirect': url_for('question', room_id=room_id)}) if is_ajax else redirect(
            url_for('question', room_id=room_id))

    # Handle failure cases with specific error messages
    if isinstance(result, dict) and result.get('success') == False:
        error_message = result.get('message', 'Could not change question.')
    else:
        error_message = 'Could not change question.'

    return handle_error(is_ajax, error_message)

def process_double_points(game_room, player_name, is_ajax, room_id, acting_player=None):
    """
    Process a request to use the double points tool.

    Args:
        game_room (GameRoom): The game room object
        player_name (str): The name of the player
        is_ajax (bool): Whether the request is an AJAX request
        room_id (str): The ID of the room
        acting_player (str, optional): The player on whose behalf the action is being taken

    Returns:
        Response: A response object if the tool was used, None otherwise
    """
    # Determine the effective player
    effective_player = player_name

    # If acting_player is provided and player is the host, use acting_player
    if acting_player and game_room.is_host(player_name) and acting_player in game_room.players:
        effective_player = acting_player
    # Otherwise, if player is the host, use the current player's name
    elif game_room.is_host(player_name):
        effective_player = game_room.current_player

    success = game_room.use_double_points(effective_player)
    if success:
        message = ''
        if game_room.is_host(player_name) and effective_player != player_name:
            # Add a game event for using the double points tool
            add_game_event(room_id, 'tool_used', {
                'player_name': player_name,
                'tool_name': 'double_points',
                'target_player': effective_player,
                'message': f'{player_name} activated Double Points for {effective_player}'
            })
        else:
            # Add a game event for using the double points tool
            add_game_event(room_id, 'tool_used', {
                'player_name': player_name,
                'tool_name': 'double_points',
                'target_player': effective_player,
                'message': f'{player_name} activated Double Points'
            })

        if is_ajax:
            return jsonify({'success': True, 'message': message})
        return True
    else:
        return False

def process_tool_request(tool_name, session, game_room, is_ajax, room_id, player_name, question_uploader, acting_player=None):
    """
    Process a request to use a game tool.

    Args:
        tool_name (str): The name of the tool being used
        session (dict): The session object
        game_room (GameRoom): The game room object
        is_ajax (bool): Whether the request is an AJAX request
        room_id (str): The ID of the room
        player_name (str): The name of the player
        question_uploader (QuestionUploader): The question uploader object
        acting_player (str, optional): The player on whose behalf the action is being taken

    Returns:
        Response: A response object based on the tool used and the result
    """
    # Get acting_player from request if not provided
    from flask import request
    if acting_player is None and 'acting_player' in request.form:
        acting_player = request.form.get('acting_player')

    if tool_name == 'double_points':
        result = process_double_points(game_room, player_name, is_ajax, room_id, acting_player)
        if isinstance(result, bool) and not is_ajax:
            return redirect(url_for('game_room', room_id=room_id))
        return result

    # Process change question tool
    response = process_change_question(tool_name, session, game_room, is_ajax, room_id, player_name, question_uploader, acting_player)
    if response:
        return response

    if is_ajax:
        return jsonify({'success': False, 'message': 'Invalid tool name.'})
    return redirect(url_for('game_room', room_id=room_id))
