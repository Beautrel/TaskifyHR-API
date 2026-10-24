from rest_framework.permissions import BasePermission


class IsManager(BasePermission):
    """Réservé aux utilisateurs dont le rôle est « manager »."""

    message = "Cet espace est réservé aux managers."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_manager)
