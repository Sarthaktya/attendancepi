from fastapi import WebSocket


class ConnectionRelay:
    """
    Holds the single Pi WebSocket connection and all connected browser sockets.
    Relays frames and events between them.

    Note: this uses in-memory state, so the server must run with a single worker.
    """

    def __init__(self):
        self.pi: WebSocket | None    = None
        self.browsers: set[WebSocket] = set()

    @property
    def pi_connected(self) -> bool:
        return self.pi is not None

    async def connect_pi(self, ws: WebSocket):
        await ws.accept()
        self.pi = ws
        await self.broadcast({"type": "pi_status", "connected": True})

    def disconnect_pi(self):
        self.pi = None

    async def connect_browser(self, ws: WebSocket):
        await ws.accept()
        self.browsers.add(ws)

    def disconnect_browser(self, ws: WebSocket):
        self.browsers.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for browser in self.browsers:
            try:
                await browser.send_json(message)
            except Exception:
                dead.add(browser)
        self.browsers -= dead

    async def send_to_pi(self, message: dict):
        if self.pi:
            await self.pi.send_json(message)


relay = ConnectionRelay()
