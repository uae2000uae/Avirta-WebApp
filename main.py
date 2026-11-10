# main.py - Entry point for Google Cloud Run (buildpacks serve main:app with gunicorn)

# Import the Flask app from the current directory
from app import app

# Local run: python main.py
if __name__ == '__main__':
    # Cloud Run serves the app with gunicorn, so this block
    # is primarily for local testing
    import os

    # Determine debug/reloader from environment (default OFF; opt in explicitly).
    # Never enable the debugger unless FLASK_DEBUG=1 is set intentionally.
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'

    port = int(os.environ.get('PORT', 8080))
    # Enable Flask's built-in reloader when debug is True
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=debug)
