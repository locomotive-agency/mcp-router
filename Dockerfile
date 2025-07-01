# Use the official Docker-in-Docker image as the base.
# This image includes the Docker daemon and all its dependencies.
FROM docker:25.0-dind

# Install Python, pip, and git.
# The 'dind' image is based on Alpine Linux, so we use 'apk'.
RUN apk add --no-cache python3 py3-pip git

# Set up the working directory
WORKDIR /app

# Add the src directory to PYTHONPATH so Python can find the application module.
ENV PYTHONPATH "${PYTHONPATH}:/app/src"

# Copy the rest of the application files
COPY . .

# Install Python dependencies from requirements.txt
# We also install gunicorn to run the Flask app in production.
# The --break-system-packages flag is required to override the
# "externally-managed-environment" error (PEP 668).
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt && \
    pip3 install --no-cache-dir --break-system-packages gunicorn

# Copy the entrypoint script and make it executable
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose the port the web UI will run on
EXPOSE 8000

# Set the entrypoint to our custom script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# The command to run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "mcp_router.web:app"] 