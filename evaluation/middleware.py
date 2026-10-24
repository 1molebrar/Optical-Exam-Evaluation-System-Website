from django.http import HttpResponseRedirect
from django.urls import reverse


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Paths that don't require login
        exempt_urls = [
            '/admin/login/',
            '/admin/logout/',
            '/admin/password_change/',
            '/admin/password_change/done/',
            '/accounts/login/',
            '/accounts/logout/',
            '/accounts/',
            '/static/',
            '/media/',
        ]
        
        # Check if path is exempt
        for url in exempt_urls:
            if request.path.startswith(url):
                return self.get_response(request)
        
        # Check if user is authenticated
        if not request.user.is_authenticated:
            # Redirect to admin login
            return HttpResponseRedirect('/admin/login/')
        
        return self.get_response(request)