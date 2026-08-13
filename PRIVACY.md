# Privacy

Aylo Desktop is designed so basic speech transcription can run locally. Optional features connect to third-party services and therefore have different privacy characteristics.

## Data stored locally

The application may store the following under `%APPDATA%\Aylo`:

- Application and microphone settings
- Error logs
- Recent successful results and requests
- Downloaded or bundled speech-model files
- A local Gmail search index when Gmail sync is enabled

API keys and Gmail OAuth tokens are stored through Windows Credential Manager. The application also uses the Windows clipboard to paste generated text.

## Data sent to third parties

Depending on which feature the user enables:

- Groq receives prompts, selected clipboard content, and relevant Gmail excerpts used for AI generation.
- OpenAI receives realtime microphone audio and conversation events during realtime voice chat.
- Pollinations receives image prompts and an API credential for image generation.
- Google receives Gmail API requests when Gmail integration is connected.

Provider handling, retention, and training policies are governed by each provider's terms and the user's account configuration. Users should not enable a cloud feature for sensitive content unless its provider terms meet their needs.

## Gmail access

Gmail integration requests read, compose, and send scopes. Syncing creates a local index of selected recent messages. Drafting or sending mail occurs only after a user action in the application. Disconnecting removes the stored OAuth token, but users should separately clear the local Gmail index if they also want cached message data removed.

## Telemetry

The current source does not include a first-party analytics or telemetry service. Network requests are made for explicitly enabled provider features, application links, and provider authentication.

## Before distributing a modified build

Maintainers who add providers, telemetry, crash reporting, remote configuration, or cloud storage must update this document and provide clear notice and consent in the application.
