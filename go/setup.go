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

package main

import (
	"encoding/json"
	"fmt"
)

type BidiGenerateContentSetup struct {
	Setup Setup `json:"setup"`
}

type Setup struct {
	Model             string            `json:"model"`
	GenerationConfig  *GenerationConfig `json:"generation_config,omitempty"`
	SystemInstruction *Content          `json:"system_instruction,omitempty"`
	Tools             []ToolInterface   `json:"tools,omitempty"`
}

type GenerationConfig struct {
	ResponseModalities ResponseModalities `json:"response_modalities"`
	SpeechConfig       *SpeechConfig      `json:"speech_config,omitempty"`
}

type ResponseModalities struct {
	values []string
}

func (rm *ResponseModalities) UnmarshalJSON(data []byte) error {
	var str string
	if err := json.Unmarshal(data, &str); err == nil {
		rm.values = []string{str}
		return nil
	}

	var strSlice []string
	if err := json.Unmarshal(data, &strSlice); err == nil {
		rm.values = strSlice
		return nil
	}

	return fmt.Errorf("invalid response_modalities format: %s", string(data))
}

func (rm ResponseModalities) MarshalJSON() ([]byte, error) {
	return json.Marshal(rm.values)
}

func (rm ResponseModalities) GetValues() []string {
	return rm.values
}

type SpeechConfig struct {
	VoiceConfig struct {
		PrebuiltVoiceConfig struct {
			VoiceName string `json:"voice_name"`
		} `json:"prebuilt_voice_config"`
	} `json:"voice_config"`
}

type Content struct {
	Parts []struct {
		Text string `json:"text"`
	} `json:"parts"`
}

// ToolInterface represents an interface for different tool types.
type ToolInterface interface{} // Generic interface to accommodate various tool types

// Define specific tool types if needed (e.g., FunctionDeclarationTool, CodeExecutionTool, etc.)
// Implement ToolInterface for each tool type
