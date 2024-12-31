# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Vertex AI Gemini Multimodal Live WebSockets Proxy Server """
import os
import asyncio
import json
import ssl
import traceback
import websockets
import certifi
import logging
import google.auth
from google.auth.transport.requests import Request
from google.auth.transport import requests
from google.oauth2 import id_token
from websockets.legacy.protocol import WebSocketCommonProtocol
from websockets.legacy.server import WebSocketServerProtocol


# Configure logging 
logging.basicConfig(level=logging.INFO)  # Set the desired logging level
logging.info("Starting Gemini Multimodal Live API Proxy service")
#print("DEBUG: proxy.py - Starting script...")  # Add print here

HOST = "us-central1-aiplatform.googleapis.com"
SERVICE_URL = f"wss://{HOST}/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent"

DEBUG = True

# Track active connections
active_connections = set()


async def get_access_token():
    """Retrieves the access token for the currently authenticated account."""
    try:
        creds, _ = google.auth.default()  # Get the default credentials
        if not creds.valid:
            # Refresh the credentials if they're not valid
            request = Request()
            creds.refresh(request)
        return creds.token
    except Exception as e:
        logging.error("Error getting access token: %s", e)
        logging.error("Full traceback:\n%s", traceback.format_exc())
        # print(f"Error getting access token: {e}")
        # print(f"Full traceback:\n{traceback.format_exc()}")
        raise


async def proxy_task(
    source_websocket: WebSocketCommonProtocol,
    target_websocket: WebSocketCommonProtocol,
    name: str = "",
) -> None:
    """
    Forwards messages from one WebSocket connection to another.
    """
    try:
        async for message in source_websocket:
            try:
                data = json.loads(message)

                # Log message type for debugging
                if "setup" in data:
                    logging.debug("% forwarding setup message", name)
                    logging.debug(
                        "Setup message content: %s", json.dumps(data, indent=2)
                    )
                    # print(f"{name} forwarding setup message")
                    # print(f"Setup message content: {json.dumps(data, indent=2)}")
                elif "realtime_input" in data:
                    logging.debug("%s forwarding audio/video input", name)
                    # print(f"{name} forwarding audio/video input")
                elif "serverContent" in data:
                    has_audio = "inlineData" in str(data)
                    logging.debug(
                        "%s forwarding server content %s",
                        name,
                        " with audio" if has_audio else "",
                    )
                    # print(
                    #    f"{name} forwarding server content"
                    #    + (" with audio" if has_audio else "")
                    # )
                else:
                    logging.debug(
                        "%s forwarding message type: %s", name, list(data.keys())
                    )
                    logging.debug("Message content: %s", json.dumps(data, indent=2))
                    # print(f"{name} forwarding message type: {list(data.keys())}")
                    # print(f"Message content: {json.dumps(data, indent=2)}")

                # Forward the message
                try:
                    await target_websocket.send(json.dumps(data))
                except Exception as e:
                    logging.error("%s Error sending message:", name)
                    logging.error("=" * 80)
                    logging.error("Error details: %s", str(e))
                    logging.error("=" * 80)
                    logging.error("Message that failed: %s", json.dumps(data, indent=2))
                    # print(f"\n{name} Error sending message:")
                    # print("=" * 80)
                    # print(f"Error details: {str(e)}")
                    # print("=" * 80)
                    # print(f"Message that failed: {json.dumps(data, indent=2)}")
                    raise

            except websockets.exceptions.ConnectionClosed as e:
                logging.warning(
                    "%s Connection closed: code=%s, reason=%s", name, e.code, e.reason
                )

                print(f"\n{name} connection closed during message processing:")
                print("=" * 80)
                print(f"Close code: {e.code}")
                print(f"Close reason (full):")
                print("-" * 40)
                print(e.reason)
                print("=" * 80)
                break
            except Exception as e:
                logging.exception("%s Error processing message: %s", name, e)

                print(f"\n{name} Error processing message:")
                print("=" * 80)
                print(f"Error details: {str(e)}")
                print(f"Full traceback:\n{traceback.format_exc()}")
                print("=" * 80)

    except websockets.exceptions.ConnectionClosed as e:
        logging.warning(
            "%s Connection closed: code=%s, reason=%s", name, e.code, e.reason
        )
    except Exception as e:
        logging.exception("%s Error processing message: %s", name, e)

    finally:
        # Clean up connections when done
        logging.debug("%s Cleaning up connection", name)
        # print(f"{name} cleaning up connection")
        if target_websocket in active_connections:
            active_connections.remove(target_websocket)
        try:
            await target_websocket.close()
        except Exception as e:
            logging.warning("%s Error closing connection: %s", name, e)


async def create_proxy(
    client_websocket: WebSocketCommonProtocol, bearer_token: str
) -> None:
    """
    Establishes a WebSocket connection to the server and creates two tasks for
    bidirectional message forwarding between the client and the server.
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

        logging.info("Connecting to %s", SERVICE_URL)

        async with websockets.connect(
            SERVICE_URL,
            additional_headers=headers,
            ssl=ssl.create_default_context(cafile=certifi.where()),
        ) as server_websocket:
            logging.info("Connected to Vertex AI Gemini Multimodal Live API")
            # print("Connected to Vertex AI")
            active_connections.add(server_websocket)

            # Create bidirectional proxy tasks
            client_to_server = asyncio.create_task(
                proxy_task(client_websocket, server_websocket, "Client->Server")
            )
            server_to_client = asyncio.create_task(
                proxy_task(server_websocket, client_websocket, "Server->Client")
            )

            try:
                # Wait for both tasks to complete
                await asyncio.gather(client_to_server, server_to_client)
            except Exception as e:
                logging.exception("Error during proxy operation: %s", e)
                # print(f"Error during proxy operation: {e}")
                # print(f"Full traceback: {traceback.format_exc()}")
            finally:
                # Clean up tasks
                for task in [client_to_server, server_to_client]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

    except Exception as e:
        logging.exception("Error creating proxy connection: %s", e)
        # print(f"Error creating proxy connection: {e}")
        # print(f"Full traceback: {traceback.format_exc()}")


async def handle_client(client_websocket: WebSocketServerProtocol) -> None:
    """
    Handles a new client connection.
    """

    logging.info("New connection ...")
    #print("New connection...")
    try:
        # Check for IAP JWT Assertion
        # Check if running on Cloud Run (IAP enabled)
        if os.environ.get('K_SERVICE'):  # K_SERVICE env var is present on Cloud Run
            try:
                headers = client_websocket.headers
                iap_jwt_assertion = headers.get('X-Goog-IAP-JWT-Assertion')

                if iap_jwt_assertion:
                    try:
                        # Validate the JWT assertion and extract user info
                        id_info = id_token.verify_oauth2_token(
                            iap_jwt_assertion,
                            requests.Request(),
                            "882920967572-tq7nqgstl4l5q3m0hcst8b331ur89s1v.apps.googleusercontent.com" 
                        )

                        user_email = id_info['email']
                        logging.info("WebSocket connection established by: %s", user_email)

                    except ValueError as e:
                        logging.error("Invalid IAP JWT assertion: %s", e)
                        await client_websocket.close(code=1011, reason="Invalid IAP JWT assertion")
                        return

                else:
                    logging.warning("Missing IAP JWT assertion header")
                    await client_websocket.close(code=1011, reason="Missing IAP JWT assertion")
                    return
            except AttributeError:
                logging.warning("No request headers found. This might not be an upgraded WebSocket connection.")

        else:
            logging.info("Running locally - skipping IAP JWT verification")

        # Get auth token automatically
        bearer_token = await get_access_token()
        logging.info("Retrieved bearer token automatically")

        # Send auth complete message to client
        await client_websocket.send(json.dumps({"authComplete": True}))
        logging.info("Sent auth complete message")

        logging.info("Creating proxy connection")
        await create_proxy(client_websocket, bearer_token)

    except asyncio.TimeoutError:
        logging.exception("Timeout in handle_client")
        # print("Timeout in handle_client")
        await client_websocket.close(code=1008, reason="Auth timeout")
    except Exception as e:
        logging.exception("Error in handle_client: %s", e)
        # print(f"Error in handle_client: {e}")
        # print(f"Full traceback: {traceback.format_exc()}")
        await client_websocket.close(code=1011, reason=str(e))


async def cleanup_connections() -> None:
    """
    Periodically clean up stale connections
    """
    while True:
        logging.debug("Active connections: %s", len(active_connections))
        # print(f"Active connections: {len(active_connections)}")
        for conn in list(active_connections):
            try:
                await conn.ping()
            except Exception as e:
                logging.info("Found stale connection, removing: %s", e)
                # print("Found stale connection, removing...")
                active_connections.remove(conn)
                try:
                    await conn.close()
                except Exception as e:
                    logging.warning("Error closing stale connection: %s", e)

        await asyncio.sleep(30)  # Check every 30 seconds


async def main() -> None:
    """
    Starts the WebSocket server.
    """

    logging.info("Starting WebSocket server...")
    # print(f"DEBUG: proxy.py - main() function started")
    # Get the port from the environment variable, defaulting to 8081
    # port = int(os.environ.get("PORT", 8081))
    port = 8081

    # Start the cleanup task
    cleanup_task = asyncio.create_task(cleanup_connections())

    async with websockets.serve(
        handle_client,
        "0.0.0.0",
        port,
        ping_interval=30,  # Send ping every 30 seconds
        ping_timeout=10,  # Wait 10 seconds for pong
    ):
        logging.info("WebSocket server running on 0.0.0.0:%s", port)
        # print(f"Running websocket server on 0.0.0.0:{port}...")
        try:
            await asyncio.Future()  # run forever
        finally:
            cleanup_task.cancel()
            logging.info("Shutting down WebSocket server...")
            # Close all remaining connections
            for conn in list(active_connections):
                try:
                    await conn.close()
                except Exception as e:
                    logging.warning("Error closing connection during shutdown: %s", e)
            active_connections.clear()


if __name__ == "__main__":
    asyncio.run(main())
