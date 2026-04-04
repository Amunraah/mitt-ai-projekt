/**
 * AI Project - Main Entry Point (Node.js)
 * Supports switching between different AI models via OpenRouter.
 */

import OpenAI from "openai";
import dotenv from "dotenv";

// Load environment variables
dotenv.config();

// Initialize OpenRouter client
const client = new OpenAI({
  baseURL: process.env.OPENROUTER_BASE_URL || "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY,
});

// Model configurations
const MODELS = {
  hermes: process.env.DEFAULT_MODEL || "nousresearch/hermes-3-llama-3.1-70b",
  claude: "anthropic/claude-3.5-sonnet",
  qwen: "qwen/qwen-2.5-72b-instruct",
  gpt4: "openai/gpt-4o",
};

/**
 * Send a message to the AI model and get response.
 * @param {string} message - User message
 * @param {string} model - Model key from MODELS (hermes, claude, qwen, gpt4)
 * @param {string} systemPrompt - Optional system prompt
 * @returns {Promise<string>} AI response text
 */
async function chat(message, model = "hermes", systemPrompt = null) {
  const modelName = MODELS[model] || MODELS.hermes;

  const messages = [];
  if (systemPrompt) {
    messages.push({ role: "system", content: systemPrompt });
  }
  messages.push({ role: "user", content: message });

  const response = await client.chat.completions.create({
    model: modelName,
    messages,
    temperature: 0.7,
    max_tokens: 2000,
  });

  return response.choices[0].message.content;
}

/**
 * Return available model configurations.
 * @returns {object} Available models
 */
function listAvailableModels() {
  return MODELS;
}

// Example usage
async function main() {
  console.log("Available models:", Object.keys(listAvailableModels()));

  // Test with Hermes
  const response1 = await chat(
    "Hej! Vad heter du och vad kan du hjälpa mig med?",
    "hermes"
  );
  console.log(`\n[Hermes]: ${response1}`);

  // Example with system prompt
  const response2 = await chat(
    "Explain the benefits of using PostgreSQL indexes",
    "hermes",
    "You are a database expert. Keep answers concise."
  );
  console.log(`\n[Hermes with system prompt]: ${response2}`);

  // Switch to Claude
  const response3 = await chat("Vad är din favorit programmeringsspråk?", "claude");
  console.log(`\n[Claude]: ${response3}`);

  // Switch to Qwen
  const response4 = await chat("介绍一下你自己", "qwen");
  console.log(`\n[Qwen]: ${response4}`);
}

// Run if executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}

export { chat, listAvailableModels, MODELS };
