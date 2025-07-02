"""Forms for MCP Router web interface"""

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, URL, Length, ValidationError


class EnvironmentVariableForm(FlaskForm):
    """Subform for environment variable configuration"""

    key = StringField("Key", validators=[DataRequired(), Length(max=100)])
    value = StringField("Value", validators=[Length(max=500)])
    description = StringField("Description", validators=[Length(max=200)])
    required = BooleanField("Required")

    class Meta:
        csrf = False


class ServerForm(FlaskForm):
    """Form for adding/editing MCP servers"""

    name = StringField(
        "Server Name",
        validators=[DataRequired(), Length(min=2, max=100)],
        render_kw={"placeholder": "my-mcp-server"},
    )

    github_url = StringField(
        "GitHub URL",
        validators=[DataRequired(), URL()],
        render_kw={"placeholder": "https://github.com/owner/repo"},
    )

    description = TextAreaField(
        "Description",
        validators=[Length(max=500)],
        render_kw={"placeholder": "Brief description of what this server does..."},
    )

    runtime_type = SelectField(
        "Runtime Type",
        choices=[("npx", "Node.js (npx)"), ("uvx", "Python (uvx)"), ("docker", "Docker")],
        validators=[DataRequired()],
    )

    install_command = StringField(
        "Install Command",
        validators=[Length(max=500)],
        render_kw={"placeholder": "npm install or pip install -e ."},
    )

    start_command = StringField(
        "Start Command",
        validators=[DataRequired(), Length(max=500)],
        render_kw={"placeholder": "npx mcp-server or python -m mcp_server"},
    )

    # Environment variables are handled separately in the view

    def validate_github_url(self, field: StringField) -> None:
        """Validate GitHub URL format

        Args:
            field: The GitHub URL field to validate

        Raises:
            ValidationError: If URL is not a valid GitHub repository URL
        """
        import re

        if field.data:
            pattern = r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$"
            if not re.match(pattern, field.data.rstrip("/")):
                raise ValidationError("Please enter a valid GitHub repository URL")

    def validate_runtime_type(self, field: SelectField) -> None:
        """Validate runtime type is one of allowed values

        Args:
            field: The runtime type field to validate

        Raises:
            ValidationError: If runtime type is not valid
        """
        allowed_types = ["npx", "uvx", "docker"]
        if field.data not in allowed_types:
            raise ValidationError(f'Runtime type must be one of: {", ".join(allowed_types)}')


class AnalyzeForm(FlaskForm):
    """Simple form for analyzing a GitHub repository"""

    github_url = StringField(
        "GitHub URL",
        validators=[DataRequired(), URL()],
        render_kw={"placeholder": "https://github.com/owner/repo"},
    )

    def validate_github_url(self, field: StringField) -> None:
        """Validate GitHub URL format

        Args:
            field: The GitHub URL field to validate

        Raises:
            ValidationError: If URL is not a valid GitHub repository URL
        """
        import re

        if field.data:
            pattern = r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$"
            if not re.match(pattern, field.data.rstrip("/")):
                raise ValidationError("Please enter a valid GitHub repository URL")
