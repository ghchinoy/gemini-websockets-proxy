// Copyright 2024 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Package main contains the code for a WebSockets proxy server
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"strings"

	"github.com/gorilla/websocket"
	"golang.org/x/oauth2/google"
)

var (
	targetHost  = flag.String("target", "us-central1-aiplatform.googleapis.com", "host for proxy")
	proxyAddr   = flag.String("addr", ":8080", "Proxy listen address")
	logLevel    = flag.Int("log-level", 1, "Log level (0=off, 1=info, 2=debug)")
	targetWSURL string
)

// Log levels
const (
	LogLevelOff = iota
	LogLevelInfo
	LogLevelDebug
)

func main() {
	flag.Parse()

	targetWSURL = fmt.Sprintf("wss://%s/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent", *targetHost)
	log.Printf("Starting WebSocket proxy on %s", *proxyAddr)
	log.Printf("Proxying for %s", targetWSURL)

	http.HandleFunc("/", handleWebSocket)
	log.Fatal(http.ListenAndServe(*proxyAddr, nil))
}

func handleWebSocket(w http.ResponseWriter, r *http.Request) {
	logRequest(r)

	// Upgrade to WebSocket connection

	// Allow all origins (not recommended for production)
	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}

	// Allow only specific origins
	// upgrader := websocket.Upgrader{
	//     CheckOrigin: func(r *http.Request) bool {
	//         origin := r.Header.Get("Origin")
	//         return origin == "http://localhost:3000" // Replace with your client's origin
	//     },
	// }

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		logError("Upgrade failed:", err)
		return
	}
	defer conn.Close()

	// Get Bearer token using Google Cloud Go libraries
	token, err := getBearerToken()
	if err != nil {
		logError("Failed to get Bearer token:", err)
		return
	}

	// Dial target WebSocket server with Bearer token
	header := http.Header{}
	header.Add("Authorization", "Bearer "+token) // Add Bearer token header
	targetConn, _, err := websocket.DefaultDialer.Dial(targetWSURL, header)
	if err != nil {
		logError("Dial failed:", err)
		return
	}
	defer targetConn.Close()

	logInfo("WebSocket connection established")

	proxyMessages := func(src, dst *websocket.Conn, firstMessageFromClient, firstMessageFromServer bool) {
		for {
			msgType, msg, err := src.ReadMessage()
			if err != nil {
				if closeErr, ok := err.(*websocket.CloseError); ok {
					// Handle close errors gracefully
					log.Printf("WebSocket connection closed: %d, %s", closeErr.Code, closeErr.Text)

					// Optionally, inspect and modify close messages here
					// if src == conn && closeErr.Code == 1000 { // Normal closure from client
					//     // Add user_prompt to the close message or modify it as needed
					//     // ...
					// }

					break // Exit the loop
				} else {
					logError("Read message error:", err)
					break
				}
			}
			log.Printf("type: %d, msg: %s", msgType, msg)

			if src == conn { // client message
				if firstMessageFromClient {
					// Check if it's a service_url message
					var serviceURLMsg map[string]string
					err := json.Unmarshal(msg, &serviceURLMsg)
					if err == nil && serviceURLMsg["service_url"] != "" {
						logInfo("Received service_url message:", serviceURLMsg["service_url"])

						// consider using the service_url message to allow the client to
						// chose the target WebSocket endpoint
						/*
							// Update targetWSURL
							targetWSURL = serviceURLMsg["service_url"]

							// Close existing targetConn
							targetConn.Close()

							// Dial new target WebSocket server with updated targetWSURL
							targetConn, _, err = websocket.DefaultDialer.Dial(targetWSURL, header)
							if err != nil {
								logError("Dial failed:", err)
								return // Exit the proxyMessages function
							}
							defer targetConn.Close()
						*/

						continue // Skip this message and wait for the next one
					}

					// Check if it's a setup message
					var setupMsg BidiGenerateContentSetup
					err = json.Unmarshal(msg, &setupMsg)
					if err == nil {
						log.Printf("client: %s", msg)
						// Manipulate the setup message here
						logInfo("Modifying setup message")

						log.Print("Adjusting model request ...")
						if strings.HasPrefix(setupMsg.Setup.Model, "models/") {
							setupMsg.Setup.Model = fmt.Sprintf("projects/ghchinoy-genai-sa/locations/us-central1/publishers/google/%s", setupMsg.Setup.Model)
							log.Printf("Adjusted to: %s", setupMsg.Setup.Model)
						} else {
							log.Printf("Original retained: %s", setupMsg.Setup.Model)
						}

						// Remove all tools
						log.Printf("Removing tools ...")
						setupMsg.Setup.Tools = nil

						// Send the modified setup message
						log.Print("Sending setup message ...")
						modifiedMsg, err := json.Marshal(setupMsg)
						if err != nil {
							logError("Failed to marshal modified setup message:", err)
							break
						}
						log.Printf("%s", modifiedMsg)
						err = dst.WriteMessage(msgType, modifiedMsg)
						if err != nil {
							logError("Write message error:", err)
							break
						}

						firstMessageFromClient = false
						continue
					}
					// If not a setup message, proceed normally
				}
			} else if src == targetConn { // message from server
				log.Printf("server: %s", msg)
				if firstMessageFromServer {
					firstMessageFromServer = false
					continue
				}
			}

			log.Printf("Proxying message: %s", msg)
			err = dst.WriteMessage(msgType, msg)
			if err != nil {
				logError("Write message error:", err)
				break
			}
		}
	}

	// Proxy messages between client and server
	go proxyMessages(conn, targetConn, true, true) // true represents first message hasn't yet been sent
	proxyMessages(targetConn, conn, false, false)
}

// getBearerToken returns the bearer token of the account or service account running the service
func getBearerToken() (string, error) {
	ctx := context.Background()

	// Get default credentials
	creds, err := google.FindDefaultCredentials(ctx)
	if err != nil {
		return "", fmt.Errorf("failed to find default credentials: %v", err)
	}

	// Get token source
	tokenSource := creds.TokenSource

	// Get ID token
	token, err := tokenSource.Token()
	if err != nil {
		return "", fmt.Errorf("failed to get token: %v", err)
	}

	return token.AccessToken, nil
}

func logRequest(r *http.Request) {
	dump, err := httputil.DumpRequest(r, true)
	if err != nil {
		logError("Error dumping request:", err)
		return
	}
	logDebug("Incoming request:\n", string(dump))
}

func logInfo(args ...interface{}) {
	if *logLevel >= LogLevelInfo {
		log.Println(args...)
	}
}

func logDebug(args ...interface{}) {
	if *logLevel >= LogLevelDebug {
		log.Println(args...)
	}
}

func logError(args ...interface{}) {
	log.Println(args...)
}
