# Changelog

All notable changes to Claude Buddy. Downloads are on the [Releases](https://github.com/Junseung0526/claude-buddy/releases) page.

## [1.6.0] - 2026-10-30
### Added
- Reactions to command and test results: "Passed!" with a jump, "Tests failed.." with a sad face, and "Oops, error!" for failed commands (at most every 20 seconds). Declined commands are ignored.
- Usage milestones: a celebration when today's output tokens first pass 100K, 300K, 1M or 3M.
- Settings → Open at login.
- Daily update check against GitHub releases, with a menu item to get the new version. Can be turned off in Settings.
### Changed
- Short numbers drop a trailing ".0" (157K instead of 157.0K).

## [1.5.1] - 2026-10-30
### Fixed
- Speech text above the character (such as "Following you!") was cut off at the edge in English and other languages. Long text now shrinks to fit at every size.

## [1.5.0] - 2026-10-30
### Added
- Usage window: today's output and input tokens, sessions and replies, a 7-day output chart with hover values, and today's output per project.
- Interface languages: 한국어, English, 日本語, 简体中文, Español (or follow the system language). Existing users stay on Korean.
- Eight new idle moves: dance, stretch, sit, zoomies, backflip, trip, yawn and sneeze, with fewer energetic moves at night.
- Ask answers note that they are AI-generated and may be wrong.
- Third-party license notices bundled in the app; README in five languages.
### Fixed
- Speech bubbles raising an error when shown.

## [1.4.0] - 2026-10-30
### Added
- "Needs you" alert with sound and notification when Claude Code waits for an answer or permission.
- Notification when a task longer than one minute finishes.
- Today's Claude Code usage in the menu.
### Changed
- Became a general-purpose desktop pet: AWS exam tips, automatic tip bubbles and the tip interval setting were removed. Ask answers any question.

## [1.2.2] - 2026-10-30
### Security
- Gemini (`agy`) runs with `--sandbox` when answering Ask questions.
- Downloaded tips are treated as reference material only, never as instructions.

## [1.2.1] - 2026-10-30
### Changed
- Ask uses the signed-in CLI (`claude -p`, `codex exec`, `agy -p`) so no API key is needed. Falls back to a stored API key.
- Asking no longer leaves a session log, so it doesn't show up as agent work.

## [1.2.0] - 2026-10-30
### Added
- Prop animations for each kind of task (book, pencil, terminal, magnifier, globe, checklist, speech bubble, thought cloud).
- More detailed task labels with file names, search terms, domains and elapsed time.
### Changed
- Adaptive frame rate (60 / 20 / 2 fps) roughly halves average CPU use.

## [1.1.0] - 2026-10-29
### Added
- Characters for Codex (GPT) and Antigravity (Gemini) activity.
- Choice of answer model for Ask (Claude, Gemini, GPT) and API keys stored in the macOS Keychain.
### Changed
- Status switches to "Done" as soon as Claude Code finishes replying.
- Cheaper Ask answers (low-cost models, 400-token limit).
- Code split into the `claude_buddy` package.
### Fixed
- Repeated errors when tips could not be downloaded.

## [1.0.0] - 2026-10-29
- First release for macOS (Apple Silicon).

[1.6.0]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.6.0
[1.5.1]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.5.1
[1.5.0]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.5.0
[1.4.0]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.4.0
[1.2.2]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.2.2
[1.2.1]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.2.1
[1.2.0]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.2.0
[1.1.0]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.1.0
[1.0.0]: https://github.com/Junseung0526/claude-buddy/releases/tag/v1.0.0
