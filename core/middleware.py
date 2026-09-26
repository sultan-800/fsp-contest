class SecurityHeadersMiddleware:

    CSP = "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", self.CSP)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.user.is_authenticated and not request.path.startswith("/static/"):
            # тут я не кэширую персонки промежуточными прокси/браузером
            response.headers.setdefault("Cache-Control", "no-store, private")
        return response
