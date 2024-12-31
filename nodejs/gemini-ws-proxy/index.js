/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

require('dotenv').config(); // Load environment variables from .env
const { GoogleAuth } = require('google-auth-library');
const http = require('http');
const WebSocket = require('ws');


// Configuration
let host;
let endpoint;

const apiKey = process.env.GEMINI_API_KEY;
if (apiKey) { // ML Dev
    host = 'generativelanguage.googleapis.com';
    endpoint = `wss://${host}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=${apiKey}`;
} else { // Vertex AI
    host = process.env.VERTEX_AI_HOST || 'us-central1-aiplatform.sandbox.googleapis.com';
    endpoint = `wss://${host}/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent`;
}

const proxyPort = 8080; // Port the proxy server will listen on

console.log(`proxying for ${endpoint}`)

// getAccessToken returns the Google Cloud service access token
async function getAccessToken() {
    try {
        const auth = new GoogleAuth({
            scopes: "https://www.googleapis.com/auth/cloud-platform"
        });
        //const accessToken = await auth.getAccessToken()
        const client = await auth.getClient();
        const accessToken = await client.getAccessToken();

        return accessToken;
    } catch (err) {
        console.error('Failed to obtain access token:', err);
        return null;
    }
}

// Create the http server, all websocket connections start with an http request
const server = http.createServer((req, res) => {

    // Upgrade the request to a WebSocket connection
    wss.handleUpgrade(req, req.socket, Buffer.alloc(0), (clientSocket) => {
        console.log("handinging upgrade ...")

        // Access body, if needed
        /* let body = '';
        req.on('data', (chunk) => {
            body += chunk.toString(); // Assemble the message body
        });

        req.on('end', () => {
            console.log('Message body:', body);
        }); */

        // Access the headers from the original request (req.headers), if needed
        // console.log('Headers:', req.headers);

        // Create a connection to the target server
        getAccessToken().then(bearerToken => {
            console.log(`Creating a connection to ${endpoint}`)
            let options = {};

            if (!apiKey) { // Vertex AI
                // Vertex AI requires a Bearer token
                console.log(`Adding Bearer token for Vertex AI endpoint ${JSON.stringify(bearerToken.token)}`)
                options.headers =
                {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${bearerToken.token}`,
                }
                console.log(`headers: ${JSON.stringify(options.headers)}`)
            }

            const serverSocket = new WebSocket(endpoint, options)

            let messageQueue = []; // Queue for messages before serverSocket is open

            serverSocket.on('open', () => {
                console.log('Target server connection open');
                clientSocket.send('Handshake complete');

                clientSocket.on('message', (message) => {
                    console.log(`Received message from client: ${message}`);
                    if (serverSocket.readyState === WebSocket.OPEN) {
                        try {
                            const parsedMessage = JSON.parse(message);

                            // Check for 'setup' as a top-level key
                            if ('setup' in parsedMessage) {
                                console.log("Sending message as setup message to target server.");
                                if (!apiKey) { // Vertex AI Substitutions
                                    // Vertex AI model substitution
                                    const requestedModel = parsedMessage.setup.model
                                    parsedMessage.setup.model = `projects/${process.env.GOOGLE_CLOUD_PROJECT}/locations/us-central1/publishers/google/${requestedModel}`;
                                    console.log(`For Vertex AI substituted ${requestedModel} with ${parsedMessage.setup.model}.`)
                                    
                                    // Vertex AI guard for tools in message
                                    delete parsedMessage.setup.tools
                                    console.log(`For Vertex AI, removed any tool definitions.`)

                                    message = JSON.stringify(parsedMessage);
                                    console.log(message)
                                }
                                // Handle setup message
                                serverSocket.send(message);
                            } else {
                                // Normal message forwarding
                                console.log("Regular message, forwarding to target server.");
                                serverSocket.send(message);
                            }
                        } catch (err) {
                            console.error("Failed to parse message:", err);
                            // Send an error message to the client if needed
                        }
                    } else {
                        console.log('Server socket not open, queuing message');
                        messageQueue.push(message);
                    }
                });

                // Handle messages from the target server
                serverSocket.on('message', (message) => {
                    console.log(`Received message from server: ${message}`);

                    const wsResponse = JSON.parse(message)

                    if (wsResponse.setupComplete) {
                        console.log('Setup complete.');
                        clientSocket.send(message);
                    } else if (wsResponse.toolCall) {
                        console.log('Received tool call:', wsResponse.toolCall);

                        // check the toolCall.functionCalls[] for the name of the function to execute
                        const functionCalls = wsResponse.toolCall.functionCalls;
                        const functionResponses = [];

                        for (const call of functionCalls) {
                            if (call.name === 'get_weather') {
                                console.log('Executing weather function call for:', call.args.city);

                                // then execute that request
                                let mockWeatherResponse = {
                                    temperature: 212,
                                    description: "cloudy with a chance of meatballs",
                                    humidity: 105,
                                    windSpeed: -5,
                                    city: "Gemini-istan",
                                    country: "GB"
                                }
                                console.log('Weather response:', mockWeatherResponse);

                                functionResponses.push({
                                    id: call.id,
                                    name: call.name,
                                    response: {
                                        result: {
                                            object_value: mockWeatherResponse
                                        }
                                    }
                                });

                                // send the info back to the client so it can decide to show the result or not
                                clientSocket.send(JSON.stringify({
                                    tool_response: {
                                        function_responses: functionResponses
                                    }
                                }));

                                // then return the response to the server so it can continue
                                if (functionResponses.length > 0) {
                                    const toolResponse = {
                                        tool_response: {
                                            function_responses: functionResponses
                                        }
                                    };
                                    console.log('Sending tool response:', toolResponse);
                                    serverSocket.send(JSON.stringify(toolResponse));
                                }
                            }
                        }
                    } else {
                        // Forward the message to the client
                        clientSocket.send(message);
                    }

                });

            });


            /// websocket logic here
            wss.on('connection', (clientSocket, request) => {
                console.log('Client connected');

                // Construct the target WebSocket URL
                //const targetUrl = endpoint;
                // Create a connection to the target server
                //const serverSocket = new WebSocket(targetUrl);

                let messageQueue = []; // Queue for messages before serverSocket is open

                serverSocket.on('open', () => {
                    console.log('Target server connection open');

                    // Process any queued messages
                    while (messageQueue.length > 0) {
                        const message = messageQueue.shift();
                        console.log('Sending queued message to target server');
                        serverSocket.send(message);
                    }

                    clientSocket.on('message', (message) => {
                        console.log(`Received message from client: ${message}`);

                        if (serverSocket.readyState === WebSocket.OPEN) {
                            try {
                                const parsedMessage = JSON.parse(message);

                                // Check for 'setup' as a top-level key
                                if ('setup' in parsedMessage) {
                                    console.log("Sending message as setup message to target server.");
                                    console.log("message", message)
                                    // Handle setup message
                                    serverSocket.send(message);
                                } else {
                                    // Normal message forwarding
                                    console.log("Regular message, forwarding to target server.");
                                    serverSocket.send(message);
                                }
                            } catch (err) {
                                console.error("Failed to parse message:", err);
                                // Send an error message to the client if needed
                            }
                        } else {
                            console.log('Server socket not open, queuing message');
                            messageQueue.push(message);
                        }
                    });
                });

                // Handle errors on the client socket
                clientSocket.on('error', (err) => {
                    console.error(`Client socket error: ${err}`);
                });

                // Handle errors on the server socket
                serverSocket.on('error', (err) => {
                    console.error(`Server socket error: ${err}`);
                });

                // Handle client socket close
                clientSocket.on('close', () => {
                    console.log('Client disconnected');
                    // Close the connection to the target server
                    serverSocket.close();
                });

                // Handle server socket close
                serverSocket.on('close', () => {
                    console.log('Server connection closed');
                    // Close the client connection if it's still open
                    if (clientSocket.readyState === WebSocket.OPEN) {
                        clientSocket.close();
                    }
                });

            });

        });
    });
});

// Create the proxy WebSocket server
//const wss = new WebSocket.Server({ port: proxyPort });
const wss = new WebSocket.Server({ noServer: true });

server.listen(proxyPort, () => {
    console.log(`WebSocket proxy server listening on ws://localhost:${proxyPort}`);
});
