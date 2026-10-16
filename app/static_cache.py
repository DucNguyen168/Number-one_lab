from starlette.staticfiles import StaticFiles


class CachedStaticFiles(StaticFiles):
    """Cache public assets at the CDN without caching API responses."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=300, s-maxage=86400"
        return response
