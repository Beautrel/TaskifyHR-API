from django.core.exceptions import ValidationError


class TaskifyPasswordValidator:
    """Règle de l'énoncé : 12 caractères, une majuscule et un chiffre."""

    def validate(self, password, user=None):
        errors = []
        if len(password) < 12:
            errors.append(ValidationError("12 caractères minimum.", code="too_short"))
        if not any(c.isupper() for c in password):
            errors.append(ValidationError("Ajoutez une majuscule.", code="no_uppercase"))
        if not any(c.isdigit() for c in password):
            errors.append(ValidationError("Ajoutez un chiffre.", code="no_digit"))
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return "12 caractères, une majuscule et un chiffre."
