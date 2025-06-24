"""Main Flask application for MCP Router"""
import os
import logging
import asyncio
from typing import Dict, Any, Optional
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError
from mcp_router.config import get_config
from mcp_router.models import db, MCPServer, init_db
from mcp_router.forms import ServerForm, AnalyzeForm
from mcp_router.container_manager import ContainerManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(get_config())

# Initialize extensions
csrf = CSRFProtect(app)
init_db(app)

# Create a placeholder analyzer for Week 1
class PlaceholderAnalyzer:
    """Placeholder for Claude analyzer - will be implemented in Week 3"""
    def analyze_repository(self, github_url: str) -> Dict[str, Any]:
        """Return sample analysis data for testing"""
        # Extract repo name from URL
        parts = github_url.rstrip('/').split('/')
        repo_name = parts[-1] if parts else 'unknown'
        
        return {
            'name': repo_name,
            'description': f'MCP server from {repo_name}',
            'runtime_type': 'npx',
            'install_command': 'npm install',
            'start_command': f'npx {repo_name}',
            'env_variables': [
                {
                    'key': 'API_KEY',
                    'description': 'API key for the service',
                    'required': True
                }
            ]
        }


@app.route('/')
def index():
    """Dashboard showing all servers"""
    try:
        servers = MCPServer.query.filter_by(is_active=True).all()
        return render_template('index.html', servers=servers)
    except Exception as e:
        logger.error(f"Error loading servers: {e}")
        flash('Error loading servers. Please try again.', 'error')
        return render_template('index.html', servers=[])


@app.route('/servers/add', methods=['GET', 'POST'])
def add_server():
    """Add new server with GitHub analysis"""
    analyzer = PlaceholderAnalyzer()
    
    if request.method == 'POST':
        # Handle analyze button
        if 'analyze' in request.form:
            analyze_form = AnalyzeForm()
            if analyze_form.validate_on_submit():
                github_url = analyze_form.github_url.data
                try:
                    analysis = analyzer.analyze_repository(github_url)
                    return render_template('servers/add.html', 
                                         github_url=github_url,
                                         analysis=analysis)
                except Exception as e:
                    logger.error(f"Error analyzing repository: {e}")
                    return render_template('servers/add.html', 
                                         github_url=github_url,
                                         error=str(e))
            else:
                flash('Invalid GitHub URL format', 'error')
        
        # Handle save button
        elif 'save' in request.form:
            server_form = ServerForm()
            if server_form.validate_on_submit():
                try:
                    server = MCPServer(
                        name=server_form.name.data,
                        github_url=server_form.github_url.data,
                        description=server_form.description.data,
                        runtime_type=server_form.runtime_type.data,
                        install_command=server_form.install_command.data or '',
                        start_command=server_form.start_command.data
                    )
                    
                    # Add environment variables
                    env_vars = []
                    for key in request.form.getlist('env_keys[]'):
                        if key:
                            env_vars.append({
                                'key': key,
                                'value': request.form.get(f'env_value_{key}', ''),
                                'description': request.form.get(f'env_desc_{key}', '')
                            })
                    server.env_variables = env_vars
                    
                    db.session.add(server)
                    db.session.commit()
                    
                    flash(f'Server "{server.name}" added successfully!', 'success')
                    return redirect(url_for('index'))
                    
                except IntegrityError:
                    db.session.rollback()
                    flash('A server with this name already exists.', 'error')
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error saving server: {e}")
                    flash('Error saving server. Please try again.', 'error')
    
    return render_template('servers/add.html')


@app.route('/servers/<server_id>')
def server_detail(server_id: str):
    """Show server details"""
    server = MCPServer.query.get_or_404(server_id)
    return render_template('servers/detail.html', server=server)


@app.route('/servers/<server_id>/edit', methods=['GET', 'POST'])
def edit_server(server_id: str):
    """Edit server configuration"""
    server = MCPServer.query.get_or_404(server_id)
    
    if request.method == 'POST':
        form = ServerForm()
        if form.validate_on_submit():
            try:
                server.name = form.name.data
                server.github_url = form.github_url.data
                server.description = form.description.data
                server.runtime_type = form.runtime_type.data
                server.install_command = form.install_command.data or ''
                server.start_command = form.start_command.data
                
                # Update environment variables
                env_vars = []
                for key in request.form.getlist('env_keys[]'):
                    if key:
                        env_vars.append({
                            'key': key,
                            'value': request.form.get(f'env_value_{key}', ''),
                            'description': request.form.get(f'env_desc_{key}', '')
                        })
                server.env_variables = env_vars
                
                db.session.commit()
                flash('Server updated successfully!', 'success')
                return redirect(url_for('server_detail', server_id=server.id))
                
            except IntegrityError:
                db.session.rollback()
                flash('A server with this name already exists.', 'error')
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating server: {e}")
                flash('Error updating server. Please try again.', 'error')
    
    # Pre-populate form
    form = ServerForm(obj=server)
    return render_template('servers/edit.html', server=server, form=form)


@app.route('/servers/<server_id>/delete', methods=['POST'])
def delete_server(server_id: str):
    """Delete a server"""
    server = MCPServer.query.get_or_404(server_id)
    
    try:
        db.session.delete(server)
        db.session.commit()
        flash(f'Server "{server.name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting server: {e}")
        flash('Error deleting server. Please try again.', 'error')
    
    return redirect(url_for('index'))


@app.route('/servers/<server_id>/toggle', methods=['POST'])
def toggle_server(server_id: str):
    """Toggle server active status"""
    server = MCPServer.query.get_or_404(server_id)
    
    try:
        server.is_active = not server.is_active
        db.session.commit()
        
        status = 'activated' if server.is_active else 'deactivated'
        flash(f'Server "{server.name}" {status}!', 'success')
        
        # If called via HTMX, return updated card
        if request.headers.get('HX-Request'):
            return render_template('partials/server_card.html', server=server)
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling server: {e}")
        flash('Error updating server status.', 'error')
    
    return redirect(url_for('server_detail', server_id=server.id))


@app.route('/api/servers/<server_id>/test', methods=['POST'])
def test_server(server_id: str):
    """
    Test server connection by spawning a container (htmx endpoint).
    """
    # This check is temporary until full async support is in place for Flask
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    manager = ContainerManager()
    result = loop.run_until_complete(manager.test_server_spawn(server_id))
    
    if result.get("status") == "success":
        return f'<div class="text-green-600">✓ {result["message"]} ({result["details"]})</div>'
    else:
        return f'<div class="text-red-600">✗ {result["message"]} ({result.get("details", "No details")})</div>'


@app.route('/config/claude-desktop')
def claude_desktop_config():
    """Generate Claude Desktop configuration"""
    config = {
        "mcpServers": {
            "mcp-router": {
                "command": "mcp-router"
            }
        }
    }
    
    # Return as downloadable JSON
    response = jsonify(config)
    response.headers['Content-Disposition'] = 'attachment; filename=claude_desktop_config.json'
    return response


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    logger.error(f"Server error: {e}")
    return render_template('500.html'), 500


@app.context_processor
def utility_processor():
    """Add utility functions to templates"""
    return {
        'len': len,
        'str': str,
    }


# Application is run from run.py at the project root 