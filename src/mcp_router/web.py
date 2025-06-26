"""Web server entry point"""

from mcp_router.app import app
from mcp_router.models import db


def main():
    """Main function to run the Flask web server."""
    # Ensure database is created
    with app.app_context():
        db.create_all()
        print("Database initialized for web server.")
    
    # Run the development server
    app.run(
        host='0.0.0.0',
        port=app.config['FLASK_PORT'],
        debug=app.config['DEBUG']
    )

if __name__ == "__main__":
    main() 