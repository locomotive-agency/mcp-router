# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP=mcp_router
ENV FLASK_ENV=production

# Copy the application source code and configuration files
COPY pyproject.toml .
COPY README.md .
COPY src/ ./src/

# Install dependencies
RUN pip install --no-cache-dir .

# Expose the port the app runs on
EXPOSE 5001

# Define the command to run the application
CMD ["mcp-router"] 