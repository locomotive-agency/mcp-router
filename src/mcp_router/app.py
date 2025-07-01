"""Main Flask application for MCP Router"""
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response, Response, stream_with_context
from flask_wtf.csrf import CSRFProtect
from flask_login import login_required
from sqlalchemy.exc import IntegrityError
from mcp_router.config import get_config
from mcp_router.models import db, MCPServer, init_db
from mcp_router.forms import ServerForm, AnalyzeForm
from mcp_router.container_manager import ContainerManager
from mcp_router.claude_analyzer import ClaudeAnalyzer
from mcp_router.auth import init_auth
from mcp_router.server_manager import init_server_manager
from mcp_router.mcp_oauth import create_oauth_blueprint, verify_token

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(get_config())

# Initialize extensions
csrf = CSRFProtect(app)
init_db(app)
init_auth(app)  # Initialize authentication

# Initialize server manager with app context
server_manager = init_server_manager(app)

# Register OAuth blueprint for MCP server authentication
oauth_bp = create_oauth_blueprint()
app.register_blueprint(oauth_bp)

# Exempt OAuth endpoints from CSRF protection
csrf.exempt(oauth_bp)


@app.route('/mcp/', defaults={'subpath': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/mcp/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy_mcp_request(subpath):
    """
    Proxy MCP requests to the actual MCP server running on port 8001.
    This allows us to serve MCP through the main Flask app port.
    """
    import httpx
    
    # Get the current MCP server status
    status = server_manager.get_status()
    
    # Check if server is running and is HTTP transport
    if not status or status['status'] != 'running' or status.get('transport') != 'http':
        return jsonify({
            'error': 'MCP server is not running in HTTP mode'
        }), 503
    
    # Get the internal URL for the MCP server
    connection_info = status.get('connection_info', {})
    internal_url = connection_info.get('internal_url')
    if not internal_url:
        return jsonify({'error': 'MCP server URL not found'}), 503
    
    # Check authentication
    auth_type = connection_info.get('auth_type', 'api_key')
    
    if auth_type == 'oauth':
        # Validate OAuth token
        auth_header = request.headers.get('authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization required', 'error_description': 'Bearer token required'}), 401
        
        token = auth_header[7:]
        payload = verify_token(token)
        if not payload:
            return jsonify({'error': 'Invalid token', 'error_description': 'Token is invalid or expired'}), 401
        
        # Token is valid, continue with request
        logger.info(f"OAuth request validated for user: {payload.get('sub')}")
    
    # Construct the full URL with the subpath
    target_url = f"{internal_url.rstrip('/')}/{subpath}"
    
    # Forward headers, filtering out some that shouldn't be forwarded
    headers_to_skip = {'host', 'content-length', 'connection', 'upgrade', 'x-forwarded-for', 'x-real-ip'}
    headers = {
        k: v for k, v in request.headers.items() 
        if k.lower() not in headers_to_skip
    }
    
    # Add/update the authorization header if we have an API key (not OAuth)
    if auth_type == 'api_key':
        api_key = connection_info.get('api_key')
        if api_key and 'authorization' not in headers:
            headers['Authorization'] = f'Bearer {api_key}'
    
    try:
        # For streaming responses (SSE/event-stream)
        if request.headers.get('accept', '').find('text/event-stream') != -1:
            def generate():
                with httpx.stream(
                    request.method,
                    target_url,
                    headers=headers,
                    content=request.get_data(),
                    timeout=None
                ) as response:
                    for chunk in response.iter_bytes():
                        yield chunk
            
            return Response(
                stream_with_context(generate()),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            # For regular requests
            response = httpx.request(
                request.method,
                target_url,
                headers=headers,
                content=request.get_data(),
                timeout=30.0
            )
            
            # Create Flask response with the proxied content
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in excluded_headers
            }
            
            return Response(
                response.content,
                response.status_code,
                headers
            )
            
    except httpx.TimeoutException:
        return jsonify({'error': 'Request to MCP server timed out'}), 504
    except Exception as e:
        logger.error(f"Error proxying MCP request: {e}")
        return jsonify({'error': 'Failed to proxy request to MCP server'}), 502

# Exempt the MCP proxy route from CSRF protection
csrf.exempt(proxy_mcp_request)


# +----------------------+
# | Main UI Routes       |
# +----------------------+

@app.route('/')
@login_required
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
@login_required
def add_server():
    """Add new server with GitHub analysis"""
    if request.method == 'POST':
        # Handle analyze button
        if 'analyze' in request.form:
            analyze_form = AnalyzeForm()
            if analyze_form.validate_on_submit():
                github_url = analyze_form.github_url.data
                try:
                    # Use the real ClaudeAnalyzer
                    analyzer = ClaudeAnalyzer()
                    analysis = analyzer.analyze_repository(github_url)
                    
                    # For HTMX requests, use a partial template
                    if request.headers.get('HX-Request'):
                        return render_template('servers/add_form.html', 
                                             github_url=github_url,
                                             analysis=analysis)
                    else:
                        return render_template('servers/add.html', 
                                             github_url=github_url,
                                             analysis=analysis)
                except Exception as e:
                    logger.error(f"Error analyzing repository '{github_url}': {e}")
                    
                    # For HTMX requests, use a partial template
                    if request.headers.get('HX-Request'):
                        return render_template('servers/add_form.html', 
                                             github_url=github_url,
                                             error=str(e))
                    else:
                        flash(f"Analysis failed: {e}", "error")
                        return render_template('servers/add.html', 
                                             github_url=github_url,
                                             error=str(e))
            else:
                flash('Invalid GitHub URL format.', 'error')
        
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
                                'key': key.strip(),
                                'value': request.form.get(f'env_value_{key}', '').strip(),
                                'description': request.form.get(f'env_desc_{key}', '').strip()
                            })
                    server.env_variables = env_vars
                    
                    db.session.add(server)
                    db.session.commit()
                    
                    flash(f'Server "{server.name}" added successfully!', 'success')
                    
                    # Handle HTMX requests with HX-Redirect to avoid duplicate headers
                    if request.headers.get('HX-Request'):
                        response = make_response('', 204)
                        response.headers['HX-Redirect'] = url_for('index')
                        return response
                    else:
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
@login_required
def server_detail(server_id: str):
    """Show server details"""
    server = MCPServer.query.get_or_404(server_id)
    return render_template('servers/detail.html', server=server)


@app.route('/servers/<server_id>/edit', methods=['GET', 'POST'])
@login_required
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
                            'key': key.strip(),
                            'value': request.form.get(f'env_value_{key}', '').strip(),
                            'description': request.form.get(f'env_desc_{key}', '').strip()
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
@login_required
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
@login_required
def toggle_server(server_id: str):
    """Toggle server active status"""
    server = MCPServer.query.get_or_404(server_id)
    
    try:
        server.is_active = not server.is_active
        db.session.commit()
        
        status = 'activated' if server.is_active else 'deactivated'
        flash(f'Server "{server.name}" {status}!', 'success')
        
        # For HTMX request, redirect to refresh the page
        if request.headers.get('HX-Request'):
            response = make_response('', 204)
            response.headers['HX-Refresh'] = 'true'
            return response
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling server: {e}")
        flash('Error updating server status.', 'error')
    
    return redirect(url_for('server_detail', server_id=server.id))


@app.route('/api/servers/<server_id>/test', methods=['POST'])
@login_required
def test_server(server_id: str):
    """
    Test server connection by spawning a container (htmx endpoint).
    """
    manager = ContainerManager(app)
    result = manager.test_server(server_id)
    
    if result.get("status") == "success":
        return f'<div class="text-green-600">✓ Server test successful! Exit code: {result["exit_code"]}</div>'
    else:
        return f'<div class="text-red-600">✗ {result["message"]} ({result.get("stderr", "No details")})</div>'


@app.route('/config/claude-desktop')
@login_required
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


@app.route('/config/local-inspector')
@login_required
def local_inspector_config():
    """Generate a configuration file for the local MCP Inspector."""
    config = {
        "mcpServers": {
            "mcp-router-dev": {
                "command": "python",
                "args": ["-m", "mcp_router.server"],
                "env": {
                    "PYTHONPATH": os.getcwd()
                }
            }
        }
    }
    response = jsonify(config)
    response.headers['Content-Disposition'] = 'attachment; filename=inspector_config.json'
    return response


@app.route('/mcp-control')
@login_required
def mcp_control():
    """MCP Server Control Panel"""
    return render_template('mcp_control.html')


@app.route('/api/mcp/start', methods=['POST'])
@login_required
def start_mcp_server():
    """Start the MCP server with specified transport"""
    data = request.get_json() or {}
    transport = data.get('transport', 'stdio')
    
    # Validate transport
    if transport not in ['stdio', 'http']:
        return jsonify({
            'status': 'error',
            'message': 'Invalid transport. Must be stdio or http'
        }), 400
    
    # Set transport-specific parameters
    kwargs = {}
    if transport == 'http':
        # For HTTP, we no longer need host/port/path from the client.
        # We use standard defaults for the internal server.
        kwargs['host'] = '127.0.0.1'
        kwargs['port'] = 8001
        kwargs['path'] = '/mcp'
        
        # Check authentication mode
        auth_mode = data.get('auth_mode', 'api_key')
        if auth_mode == 'oauth':
            kwargs['enable_oauth'] = True
        else:
            kwargs['api_key'] = data.get('api_key')
    
    result = server_manager.start_server(transport, **kwargs)
    
    if result['status'] == 'success':
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route('/api/mcp/stop', methods=['POST'])
@login_required
def stop_mcp_server():
    """Stop the running MCP server"""
    result = server_manager.stop_server()
    
    if result['status'] == 'success':
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route('/api/mcp/status', methods=['GET'])
@login_required
def get_mcp_status():
    """Get current MCP server status"""
    status = server_manager.get_status()
    
    # Return HTML for htmx requests
    if request.headers.get('HX-Request'):
        return render_template('partials/mcp_status.html', status=status)
    
    # Return JSON for API requests
    return jsonify(status)


@app.route('/api/mcp/logs', methods=['GET'])
@login_required
def get_mcp_logs():
    """Get MCP server logs"""
    pid = request.args.get('pid', type=int)
    lines = request.args.get('lines', 50, type=int)
    
    if not pid:
        return jsonify({'error': 'PID parameter required'}), 400
    
    try:
        logs = server_manager.get_logs(pid, lines)
        return jsonify({'logs': logs})
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/favicon.ico')
def favicon():
    """Return empty favicon to avoid 404 errors"""
    return '', 204


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