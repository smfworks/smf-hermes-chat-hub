# Hermes Hub - Changelog

## [1.1.0] - 2025-05-18

### Added
- **Session persistence**: Conversations survive backend restarts via `~/.hermes-hub-sessions.json`
- **Auto-retry with backoff**: Transient errors (rate limits, timeouts) automatically retry up to 2 times
- **Manual retry button**: Failed messages show an inline "Retry" button
- **Request cancellation**: Cancel button kills in-flight requests (both frontend fetch and backend subprocess)
- **Error classification**: Backend marks errors as `recoverable` or permanent
- **Concurrent request protection**: Returns 429 if a request is already in progress for a profile
- **Health polling**: Status indicator refreshes every 30 seconds
- **Toast notifications**: Non-blocking status messages for actions like "Chat cleared" and "Request cancelled"
- **Keyboard shortcut**: Escape key returns to grid view
- **`DELETE /cancel/{profile}`** endpoint: Kills running subprocess for a profile
- **`start.py`**: Convenience script to launch both backend and frontend servers

### Changed
- Backend uses `subprocess.Popen` instead of `subprocess.run` for cancellable requests
- Frontend now uses `AbortController` for request cancellation
- Error display now includes context about recoverability
- Session state synced between frontend localStorage and backend disk storage

### Fixed
- API interruptions no longer kill the chat session — auto-retry and manual retry available
- Backend restarts no longer lose conversation context
- Double-submitting a message returns clear 429 error instead of concurrent subprocess chaos

## [1.0.0] - 2025-05-17

### Added
- Initial release
- Multi-profile chat UI with agent cards
- Session resume via `hermes --resume`
- Markdown rendering for agent responses
- Health check endpoint
- Tailscale-compatible networking