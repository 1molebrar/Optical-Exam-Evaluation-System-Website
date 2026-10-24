from django.core.exceptions import PermissionDenied
from functools import wraps
from django.contrib.auth.models import User


def is_admin(user):
    """Check if user is a superuser (Admin)"""
    return user.is_authenticated and (user.is_superuser or user.is_staff)


def is_instructor(user):
    """Check if user is an Instructor (staff but not superuser)"""
    return user.is_authenticated and user.is_staff and not user.is_superuser


def is_admin_or_instructor(user):
    """Check if user is either admin or instructor"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def admin_required(view_func):
    """Decorator to require admin access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can access this page.")
        return view_func(request, *args, **kwargs)
    return wrapper


def instructor_required(view_func):
    """Decorator to require instructor access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_admin_or_instructor(request.user):
            raise PermissionDenied("You must be an admin or instructor to access this page.")
        return view_func(request, *args, **kwargs)
    return wrapper


def instructor_only(view_func):
    """Decorator to allow only instructors (not admins)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_instructor(request.user):
            raise PermissionDenied("Only instructors can access this page.")
        return view_func(request, *args, **kwargs)
    return wrapper


class AdminRequiredMixin:
    """Mixin to require admin access for class-based views"""
    def dispatch(self, request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can access this page.")
        return super().dispatch(request, *args, **kwargs)


class InstructorRequiredMixin:
    """Mixin to require instructor access for class-based views"""
    def dispatch(self, request, *args, **kwargs):
        if not is_admin_or_instructor(request.user):
            raise PermissionDenied("You must be an admin or instructor to access this page.")
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin:
    """Mixin that filters querysets based on user role"""
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # If admin, return all records
        if is_admin(self.request.user):
            return queryset
        
        # If instructor, filter to their own courses
        if is_instructor(self.request.user):
            return queryset.filter(teacher=self.request.user)
        
        # For any other user, return empty queryset
        return queryset.none()