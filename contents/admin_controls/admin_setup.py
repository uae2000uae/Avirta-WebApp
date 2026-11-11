"""
Admin Setup Module for Avirta

This module handles administrative functions such as configuring game settings,
managing user permissions, and monitoring game activity.
"""
import os
import json
from datetime import datetime
from questionmanagement.ai_engine import config as ai_engine_config

# Flat settings from the old AI settings page, migrated into 'ai_config'.
_LEGACY_AI_PREFIXES = ('openai_', 'anthropic_')
_LEGACY_AI_KEYS = {'ai_provider'}
# Old "Look and Feel" colour/spacing settings from the removed theme system.
# The site now has a single design (light + dark mode, chosen per visitor),
# so these keys are ignored when old settings files are loaded.
_LEGACY_LOOK_PREFIXES = ('primary_color', 'secondary_color', 'bg_color', 'text_color',
                         'success_', 'error_', 'info_', 'border_', 'spacing_', 'font_')
_LEGACY_LOOK_KEYS = {'box_shadow', 'line_height', 'selected_theme'}


def is_legacy_look_setting(key):
    """True for settings that belonged to the removed colour-theme system."""
    return key in _LEGACY_LOOK_KEYS or key.startswith(_LEGACY_LOOK_PREFIXES)

class AdminSetup:
    """
    A class to handle administrative setup and controls for the Avirta game.

    Attributes:
        admins (dict): Dictionary of admin users and their permission levels
        game_settings (dict): Dictionary of game configuration settings
        active_sessions (list): List of currently active game sessions
        logs (list): List of system logs and events
    """

    # Permission levels
    PERMISSION_LEVELS = {
        'SUPER_ADMIN': 100,
        'ADMIN': 75,
        'MODERATOR': 50,
        'CONTENT_CREATOR': 25,
        'VIEWER': 10
    }

    # Recognised log severity levels (ordered by importance)
    LOG_LEVELS = ('INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL')

    # Recognised log categories used to group events on the dashboard
    LOG_CATEGORIES = ('GAMEPLAY', 'CONTENT', 'SYSTEM', 'GITHUB', 'AI', 'AUTH')

    # Maximum number of log entries kept in memory before the oldest are dropped
    MAX_LOGS = 1000

    # Maps raw game-event types (from add_game_event) to the counter/label used
    # on the dashboard so gameplay activity is captured automatically.
    GAME_EVENT_STATS = {
        'game_started': 'games_started',
        'game_ended': 'games_ended',
        'player_joined': 'players_joined',
        'player_left': 'players_left',
        'question_selected': 'questions_selected',
        'answer_submitted': 'answers_submitted',
        'answer_evaluated': 'answers_evaluated',
        'turn_switch': 'turn_switches',
        'tool_used': 'tools_used',
    }

    def __init__(self):
        """
        Initialize a new admin setup instance.
        """
        self.admins = {}
        self.saved_api_settings = {}
        # Initialize with default settings
        self.game_settings = {
            # Game settings
            'default_time_limit': 45,
            'max_players_per_room': 8,
            'max_categories_per_room': 7,  # Maximum number of categories per game room (3-7)
            'questions_per_category': 10,  # Number of questions per category (5-10)

            # AI question generator / validator configuration (see
            # questionmanagement/ai_engine/config.py). API keys are NOT stored
            # here - they live in Secret Manager (see ai_engine/keys.py).
            'ai_config': ai_engine_config.default_ai_config(),

        }
        self.active_sessions = []
        self.logs = []
        # Named counters accumulating important stats over the process lifetime
        # (e.g. games_started, git_pushes, errors). In-memory only, reset on
        # restart. Populated via record_stat()/log_event()/record_game_event().
        self.stats_counters = {}
        # Track process start so the dashboard can show uptime.
        self.start_time = datetime.now()
        # Peak number of concurrent active sessions observed this run.
        self.peak_active_sessions = 0

        # Load saved settings from file (if available)
        self.load_game_settings()
        self.load_saved_api_settings_from_file()
        self.selected_categories = []

    def add_admin(self, username, permission_level='MODERATOR'):
        """
        Add a new admin user with specified permission level.

        Args:
            username (str): Username of the admin
            permission_level (str, optional): Permission level. Defaults to 'MODERATOR'.

        Returns:
            bool: True if admin was added successfully, False otherwise
        """
        if username in self.admins:
            return False

        if permission_level not in self.PERMISSION_LEVELS:
            return False

        self.admins[username] = {
            'permission_level': permission_level,
            'permission_value': self.PERMISSION_LEVELS[permission_level]
        }

        self.log_event(f"Added admin {username} with permission level {permission_level}",
                       level='SUCCESS', category='AUTH')
        return True

    def remove_admin(self, username):
        """
        Remove an admin user.

        Args:
            username (str): Username of the admin to remove

        Returns:
            bool: True if admin was removed successfully, False otherwise
        """
        if username not in self.admins:
            return False

        del self.admins[username]
        self.log_event(f"Removed admin {username}", level='WARNING', category='AUTH')
        return True

    def update_permission(self, username, new_permission_level):
        """
        Update the permission level of an admin user.

        Args:
            username (str): Username of the admin
            new_permission_level (str): New permission level

        Returns:
            bool: True if permission was updated successfully, False otherwise
        """
        if username not in self.admins:
            return False

        if new_permission_level not in self.PERMISSION_LEVELS:
            return False

        old_level = self.admins[username]['permission_level']
        self.admins[username] = {
            'permission_level': new_permission_level,
            'permission_value': self.PERMISSION_LEVELS[new_permission_level]
        }

        self.log_event(f"Updated {username}'s permission from {old_level} to {new_permission_level}",
                       category='AUTH')
        return True

    def update_game_setting(self, setting_name, value):
        """
        Update a game setting and save it to file for persistence.

        Args:
            setting_name (str): Name of the setting to update
            value: New value for the setting

        Returns:
            bool: True if setting was updated successfully, False otherwise
        """
        if setting_name not in self.game_settings:
            return False

        # Validate specific settings with enforced limits
        if setting_name == 'questions_per_category':
            if not isinstance(value, int) or value < 5 or value > 10:
                self.log_event(f"Failed to update {setting_name}: value {value} is not within allowed range (5-10)",
                               level='WARNING', category='SYSTEM')
                return False
        elif setting_name == 'max_categories_per_room':
            if not isinstance(value, int) or value < 3 or value > 7:
                self.log_event(f"Failed to update {setting_name}: value {value} is not within allowed range (3-7)",
                               level='WARNING', category='SYSTEM')
                return False
        elif setting_name == 'max_players_per_room':
            if not isinstance(value, int) or value < 2 or value > 8:
                self.log_event(f"Failed to update {setting_name}: value {value} is not within allowed range (2-8)",
                               level='WARNING', category='SYSTEM')
                return False

        old_value = self.game_settings[setting_name]
        self.game_settings[setting_name] = value

        # Save settings to file to make changes permanent
        self.save_game_settings()

        self.record_stat('settings_changed')
        self.log_event(f"Updated game setting {setting_name} from {old_value} to {value}",
                       category='SYSTEM')
        return True

    def _make_settings_store(self):
        """Return a SettingsStore for persistence, or None to use legacy file I/O."""
        try:
            from datastore import get_backend_name, get_settings_store
            from datastore.json_backend import JsonSettingsStore
        except Exception:
            return None
        try:
            if get_backend_name() == "json":
                # Point the JSON store at the admin_controls directory.
                return JsonSettingsStore(os.path.dirname(__file__))
            return get_settings_store()
        except Exception:
            return None

    def _apply_loaded_settings(self, loaded_settings):
        """Merge loaded settings into game_settings, migrating old AI settings."""
        for key, value in loaded_settings.items():
            if key in _LEGACY_AI_KEYS or key.startswith(_LEGACY_AI_PREFIXES):
                continue
            if is_legacy_look_setting(key):
                continue
            self.game_settings[key] = value
        if isinstance(loaded_settings.get('ai_config'), dict):
            self.game_settings['ai_config'] = ai_engine_config.normalize_ai_config(loaded_settings['ai_config'])
        elif any(k in _LEGACY_AI_KEYS or k.startswith(_LEGACY_AI_PREFIXES) for k in loaded_settings):
            # One-time migration from the old flat openai_*/anthropic_* settings.
            self.game_settings['ai_config'] = ai_engine_config.migrate_legacy_settings(loaded_settings)

    def get_ai_config(self):
        """The normalized AI configuration (never contains API keys)."""
        return ai_engine_config.normalize_ai_config(self.game_settings.get('ai_config'))

    def set_ai_config(self, cfg):
        """Validate, store and persist the AI configuration."""
        self.game_settings['ai_config'] = ai_engine_config.normalize_ai_config(cfg)
        self.save_game_settings()
        self.record_stat('settings_changed')
        self.log_event("Updated AI settings", category='AI')
        return self.game_settings['ai_config']

    def save_game_settings(self):
        """
        Save the game settings to persistent storage.

        Persistence is delegated to the datastore layer (JSON files by default,
        Firestore when STATE_BACKEND=firestore), falling back to direct file I/O
        if the datastore package is unavailable.

        Returns:
            tuple: (success, message)
        """
        store = self._make_settings_store()
        if store is not None:
            try:
                store.replace('game', self.game_settings)
                self.log_event("Game settings saved to store")
                return True, "Game settings saved successfully"
            except Exception as e:
                self.log_event(f"Error saving game settings via store: {str(e)}", level='ERROR')
                # fall through to legacy file write

        try:
            settings_file_path = os.path.join(
                os.path.dirname(__file__), 'game_settings.json')
            with open(settings_file_path, 'w', encoding="utf-8") as f:
                json.dump(self.game_settings, f, indent=4, ensure_ascii=False)
            self.log_event("Game settings saved to file")
            return True, "Game settings saved successfully"
        except Exception as e:
            self.log_event(f"Error saving game settings: {str(e)}", level='ERROR')
            return False, f"Error saving game settings: {str(e)}"

    def load_game_settings(self):
        """
        Load game settings from persistent storage.

        Returns:
            tuple: (success, message)
        """
        store = self._make_settings_store()
        if store is not None:
            try:
                loaded_settings = store.get_all('game')
                if not loaded_settings:
                    self.log_event("Game settings not found in store, using defaults")
                    return False, "Game settings file not found, using defaults"
                self._apply_loaded_settings(loaded_settings)
                self.log_event("Game settings loaded from store")
                return True, "Game settings loaded successfully"
            except Exception as e:
                self.log_event(f"Error loading game settings via store: {str(e)}", level='ERROR')
                # fall through to legacy file load

        try:
            settings_file_path = os.path.join(
                os.path.dirname(__file__), 'game_settings.json')
            if not os.path.exists(settings_file_path):
                self.log_event("Game settings file not found, using defaults")
                return False, "Game settings file not found, using defaults"
            with open(settings_file_path, 'r') as f:
                loaded_settings = json.load(f)
            self._apply_loaded_settings(loaded_settings)
            self.log_event("Game settings loaded from file")
            return True, "Game settings loaded successfully"
        except Exception as e:
            self.log_event(f"Error loading game settings: {str(e)}", level='ERROR')
            return False, f"Error loading game settings: {str(e)}"

    def register_active_session(self, session_info):
        """
        Register a new active game session.

        Args:
            session_info (dict): Information about the game session

        Returns:
            bool: True if session was registered successfully
        """
        self.active_sessions.append(session_info)
        self.record_stat('sessions_registered')
        current = len(self.active_sessions)
        if current > self.peak_active_sessions:
            self.peak_active_sessions = current
        self.log_event(f"Registered new game session: {session_info.get('room_id', 'Unknown')}",
                       category='GAMEPLAY')
        return True

    def end_session(self, session_id):
        """
        End an active game session.

        Args:
            session_id (str): ID of the session to end

        Returns:
            bool: True if session was ended successfully, False otherwise
        """
        for i, session in enumerate(self.active_sessions):
            if session.get('room_id') == session_id:
                self.active_sessions.pop(i)
                self.log_event(f"Ended game session: {session_id}", category='GAMEPLAY')
                return True

        return False

    def record_stat(self, name, amount=1):
        """
        Increment a named stat counter kept in memory.

        Args:
            name (str): Counter name (e.g. 'games_started', 'errors').
            amount (int, optional): Amount to add. Defaults to 1.

        Returns:
            int: The new counter value.
        """
        if not name:
            return 0
        self.stats_counters[name] = self.stats_counters.get(name, 0) + amount
        return self.stats_counters[name]

    def get_stat(self, name, default=0):
        """Return the current value of a named stat counter."""
        return self.stats_counters.get(name, default)

    def log_event(self, event_description, level='INFO', category='SYSTEM', **details):
        """
        Log an event in the system and update stat counters.

        Backward compatible: existing callers that pass only a description keep
        working and default to an INFO/SYSTEM entry.

        Args:
            event_description (str): Human-readable description of the event.
            level (str, optional): Severity, one of LOG_LEVELS. Defaults to 'INFO'.
            category (str, optional): Grouping, one of LOG_CATEGORIES. Defaults to 'SYSTEM'.
            **details: Optional structured context stored on the entry.

        Returns:
            dict: The log entry that was recorded.
        """
        level = (level or 'INFO').upper()
        if level not in self.LOG_LEVELS:
            level = 'INFO'
        category = (category or 'SYSTEM').upper()
        if category not in self.LOG_CATEGORIES:
            category = 'SYSTEM'

        log_entry = {
            'timestamp': datetime.now(),
            'description': event_description,
            'level': level,
            'category': category,
            'details': details or {},
        }

        self.logs.append(log_entry)
        # Cap in-memory log growth by dropping the oldest entries.
        if len(self.logs) > self.MAX_LOGS:
            self.logs = self.logs[-self.MAX_LOGS:]

        # Roll the event up into aggregate counters for the dashboard.
        self.record_stat('total_events')
        self.record_stat(f'level:{level}')
        self.record_stat(f'category:{category}')

        return log_entry

    # -- Convenience wrappers so call sites read clearly -------------------
    def log_info(self, description, category='SYSTEM', **details):
        return self.log_event(description, level='INFO', category=category, **details)

    def log_success(self, description, category='SYSTEM', **details):
        return self.log_event(description, level='SUCCESS', category=category, **details)

    def log_warning(self, description, category='SYSTEM', **details):
        return self.log_event(description, level='WARNING', category=category, **details)

    def log_error(self, description, category='SYSTEM', **details):
        return self.log_event(description, level='ERROR', category=category, **details)

    def record_game_event(self, event_type, room_id=None, event_data=None):
        """
        Record a gameplay event into the stats/log stream.

        Called from the centralized add_game_event() hook so live game activity
        (games started/ended, players joining, questions answered, etc.) is
        captured automatically without touching every call site.

        Args:
            event_type (str): The raw event type (e.g. 'player_joined').
            room_id (str, optional): The room the event occurred in.
            event_data (dict, optional): Extra event context.
        """
        event_data = event_data or {}
        counter = self.GAME_EVENT_STATS.get(event_type)
        if counter:
            self.record_stat(counter)
        self.record_stat('gameplay_events')

        # Keep the human-readable message when one is available.
        message = event_data.get('message') or f"Game event: {event_type}"
        if room_id:
            message = f"[{room_id}] {message}"
        self.log_event(message, level='INFO', category='GAMEPLAY',
                       event_type=event_type, room_id=room_id)

    def get_logs(self, count=10, level=None, category=None):
        """
        Get the most recent system logs, optionally filtered.

        Args:
            count (int, optional): Max number of logs to retrieve. Defaults to 10.
            level (str, optional): Only return entries with this severity.
            category (str, optional): Only return entries in this category.

        Returns:
            list: List of recent log entries (most recent last).
        """
        logs = self.logs
        if level:
            level = level.upper()
            logs = [l for l in logs if l.get('level') == level]
        if category:
            category = category.upper()
            logs = [l for l in logs if l.get('category') == category]
        return logs[-count:] if logs else []

    def get_uptime(self):
        """Return a human-readable uptime string since process start."""
        delta = datetime.now() - self.start_time
        total_seconds = int(delta.total_seconds())
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return ' '.join(parts)

    def get_stats(self):
        """
        Build a structured snapshot of important system stats for the dashboard.

        Returns:
            dict: Aggregated counters grouped by area (overview, gameplay,
                  content, github, system), plus per-level/per-category totals.
        """
        # Track peak concurrency as a side effect of reading current state.
        current_sessions = len(self.active_sessions)
        if current_sessions > self.peak_active_sessions:
            self.peak_active_sessions = current_sessions

        def c(name):
            return self.stats_counters.get(name, 0)

        return {
            'overview': {
                'active_sessions': current_sessions,
                'peak_active_sessions': self.peak_active_sessions,
                'admin_users': len(self.admins),
                'uptime': self.get_uptime(),
                'total_events': c('total_events'),
            },
            'gameplay': {
                'games_started': c('games_started'),
                'games_ended': c('games_ended'),
                'players_joined': c('players_joined'),
                'players_left': c('players_left'),
                'questions_selected': c('questions_selected'),
                'answers_evaluated': c('answers_evaluated'),
                'turn_switches': c('turn_switches'),
            },
            'content': {
                'ai_generations': c('ai_generations'),
                'questions_saved': c('questions_saved'),
                'bulk_imports': c('bulk_imports'),
                'questions_reported': c('questions_reported'),
                'settings_changed': c('settings_changed'),
            },
            'github': {
                'question_pushes': c('github_question_pushes'),
                'full_source_pushes': c('github_full_pushes'),
                'auto_pushes': c('github_auto_pushes'),
                'push_failures': c('github_push_failures'),
            },
            'system': {
                'logins': c('logins'),
                'errors': c('level:ERROR') + c('level:CRITICAL'),
                'warnings': c('level:WARNING'),
            },
            'by_level': {lvl: c(f'level:{lvl}') for lvl in self.LOG_LEVELS},
            'by_category': {cat: c(f'category:{cat}') for cat in self.LOG_CATEGORIES},
        }

    def has_permission(self, username, required_level):
        """
        Check if a user has the required permission level.

        Args:
            username (str): Username to check
            required_level (str): Required permission level

        Returns:
            bool: True if user has required permission, False otherwise
        """
        if username not in self.admins:
            return False

        if required_level not in self.PERMISSION_LEVELS:
            return False

        user_level = self.admins[username]['permission_value']
        required_value = self.PERMISSION_LEVELS[required_level]

        return user_level >= required_value

    def select_categories(self, categories, username=None, required_level='MODERATOR'):
        """
        Select up to 5 categories for a game session.

        Args:
            categories (list): List of category IDs to select
            username (str, optional): Username of the admin making the selection. Defaults to None.
            required_level (str, optional): Required permission level. Defaults to 'MODERATOR'.

        Returns:
            tuple: (success, message or selected categories)
        """
        # Check permissions if username is provided
        if username and not self.has_permission(username, required_level):
            return False, "Insufficient permissions to select categories"

        # Limit to max_categories_per_room (default is 7)
        max_categories = self.game_settings.get('max_categories_per_room', 7)
        # Ensure max_categories is within valid range (3-7)
        max_categories = max(3, min(7, max_categories))
        if len(categories) > max_categories:
            categories = categories[:max_categories]

        # Store the selected categories
        self.selected_categories = categories

        # Log the event
        self.log_event(f"Selected categories: {', '.join(categories)}")

        return True, self.selected_categories

    def set_question_timer(self, seconds, username=None, required_level='MODERATOR'):
        """
        Set the timer for answering questions.

        Args:
            seconds (int): Number of seconds for the timer
            username (str, optional): Username of the admin making the change. Defaults to None.
            required_level (str, optional): Required permission level. Defaults to 'MODERATOR'.

        Returns:
            tuple: (success, message)
        """
        # Check permissions if username is provided
        if username and not self.has_permission(username, required_level):
            return False, "Insufficient permissions to set timer"

        # Validate the timer value
        if not isinstance(seconds, int) or seconds < 5 or seconds > 120:
            return False, "Timer must be between 5 and 120 seconds"

        # Update the game setting
        success = self.update_game_setting('default_time_limit', seconds)

        if success:
            return True, f"Question timer set to {seconds} seconds"
        else:
            return False, "Failed to update timer setting"

    def get_selected_categories(self):
        """
        Get the currently selected categories.

        Returns:
            list: List of selected category IDs
        """
        return self.selected_categories

    def save_api_settings_to_file(self):
        """
        Save the saved API settings to a JSON file for persistence.

        Returns:
            tuple: (success, message)
        """
        try:
            # Path to the settings file
            settings_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                             'admin_controls', 'saved_api_settings.json')

            # Save the settings to the file
            with open(settings_file_path, 'w', encoding="utf-8") as f:
                json.dump(self.saved_api_settings, f, indent=4, ensure_ascii=False)

            self.log_event("Saved API settings saved to file")
            return True, "Saved API settings saved successfully"
        except Exception as e:
            self.log_event(f"Error saving API settings: {str(e)}", level='ERROR')
            return False, f"Error saving API settings: {str(e)}"

    def load_saved_api_settings_from_file(self):
        """
        Load saved API settings from a JSON file.

        Returns:
            tuple: (success, message)
        """
        try:
            # Path to the settings file
            settings_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                             'admin_controls', 'saved_api_settings.json')

            # Check if the file exists
            if not os.path.exists(settings_file_path):
                self.log_event("Saved API settings file not found, using empty dictionary")
                return False, "Saved API settings file not found, using empty dictionary"

            # Load the settings from the file
            with open(settings_file_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            migrated = {name: ai_engine_config.normalize_preset(value)
                        for name, value in (loaded or {}).items() if isinstance(value, dict)}
            self.saved_api_settings = migrated
            if migrated != loaded:
                self.save_api_settings_to_file()  # rewrite once in the new format

            self.log_event("Saved API settings loaded from file")
            return True, "Saved API settings loaded successfully"
        except Exception as e:
            self.log_event(f"Error loading saved API settings: {str(e)}", level='ERROR')
            return False, f"Error loading saved API settings: {str(e)}"

    def save_api_settings(self, name, values):
        """Save (or overwrite) a named AI preset.

        A preset is {"option", "model", "quality", "advanced", ["api_format", "base_url"], "note"}.
        Presets never contain API keys.
        """
        if not name or not name.strip():
            return False, "Preset name cannot be empty"
        preset = ai_engine_config.normalize_preset(values)
        self.saved_api_settings[name.strip()] = preset
        success, message = self.save_api_settings_to_file()
        if not success:
            return False, f"Failed to save the preset: {message}"
        self.log_event(f"AI preset saved as '{name.strip()}'", category='AI')
        return True, f"Preset '{name.strip()}' saved"

    def get_saved_api_settings(self):
        """
        Get all saved API settings.

        Returns:
            dict: Dictionary of saved API settings
        """
        return self.saved_api_settings

    def delete_api_settings(self, name):
        """
        Delete saved API settings by name.

        Args:
            name (str): Name of the saved settings to delete

        Returns:
            tuple: (success, message)
        """
        if name not in self.saved_api_settings:
            return False, f"No saved settings found with name '{name}'"

        # Delete the saved settings
        del self.saved_api_settings[name]

        # Save to file to make changes permanent
        success, message = self.save_api_settings_to_file()
        if not success:
            return False, f"Failed to save changes permanently: {message}"

        self.log_event(f"Deleted API settings '{name}'")
        return True, f"Deleted API settings '{name}'"

