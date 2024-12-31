# WebSockets proxy for Gemini Multimodal Live API

Proxy services in various languages for the Vertex AI Gemini Multimodal Live WebSockets API.

Please note, for all of these, the Gemini agent proxy doesn't do anything by itself - you'll need a frontend client to interact with these proxies. In the future, sample frontends will be provided to test the proxies themselves.


## Go

This uses the gorilla/websocket library which, by default, enforces the origin of the WebSocket connection for security reasons. This prevents cross-site WebSocket hijacking attacks.


## Python

This is the python proxy used within the [Gemini Multimodal Live Dev Guide](https://github.com/heiko-hotz/gemini-multimodal-live-dev-guide)


## Nodejs

This is a variation of the proxy used for the [Gemini Multimodal Live Dev Guide](https://github.com/heiko-hotz/gemini-multimodal-live-dev-guide) but in NodeJS.


## Frontend Examples

A future placeholder for example frontends.


# Disclaimer

This is not an officially supported Google project.