"""Tests for authentication type database migration"""

from sqlalchemy import text
from mcp_router.models import db, MCPServerStatus


class TestAuthMigration:
    """Test authentication migration functionality"""

    def test_auth_type_column_addition(self, app):
        """Test auth_type column is added during migration"""
        with app.app_context():
            # Verify auth_type column exists (should be created by the new schema)
            result = db.session.execute(text("PRAGMA table_info(mcp_server_status)")).fetchall()
            column_names = [row[1] for row in result]

            assert "auth_type" in column_names

    def test_default_auth_type_value(self, app):
        """Test default auth_type value assignment during migration"""
        with app.app_context():
            # Create a status record and verify default
            status = MCPServerStatus(transport="http", status="running")
            db.session.add(status)
            db.session.commit()

            assert status.auth_type == "api_key"

    def test_migration_with_oauth_enabled(self, app):
        """Test that status record can be created with oauth auth_type"""
        with app.app_context():
            # Create status record with oauth
            status = MCPServerStatus(transport="http", status="running", auth_type="oauth")
            db.session.add(status)
            db.session.commit()

            assert status.auth_type == "oauth"

    def test_auth_type_column_constraints(self, app):
        """Test auth_type column has proper constraints"""
        with app.app_context():
            # Verify column info
            result = db.session.execute(text("PRAGMA table_info(mcp_server_status)")).fetchall()

            auth_type_column = None
            for row in result:
                if row[1] == "auth_type":  # column name
                    auth_type_column = row
                    break

            assert auth_type_column is not None
            # Check that column exists and has some type definition
            assert "VARCHAR" in auth_type_column[2] or "TEXT" in auth_type_column[2]
            assert auth_type_column[3] == 1  # not null

    def test_auth_type_value_validation(self, app):
        """Test that valid auth_type values can be stored"""
        with app.app_context():
            # Test oauth value
            status_oauth = MCPServerStatus(transport="http", status="running", auth_type="oauth")
            db.session.add(status_oauth)
            db.session.commit()

            # Test api_key value
            status_api = MCPServerStatus(transport="stdio", status="running", auth_type="api_key")
            db.session.add(status_api)
            db.session.commit()

            # Verify both are stored correctly
            oauth_record = MCPServerStatus.query.filter_by(auth_type="oauth").first()
            api_record = MCPServerStatus.query.filter_by(auth_type="api_key").first()

            assert oauth_record is not None
            assert api_record is not None
            assert oauth_record.auth_type == "oauth"
            assert api_record.auth_type == "api_key"
