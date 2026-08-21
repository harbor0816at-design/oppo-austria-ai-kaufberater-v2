# DeepSeek Main-Agent routing

The assistant now uses DeepSeek as the primary conversational intelligence.
Source systems are policy tools, not the brain of the assistant.

## Routes

| Route | Behavior |
| --- | --- |
| `direct` | DeepSeek answers ordinary/general questions directly. Google Sheets is not read. |
| `official` | Current/official OPPO facts are grounded in Google Sheets Source_B before DeepSeek answers. |
| `recommendation` | DeepSeek understands the user need; current OPPO models are selected only from Source_B. |
| `current_external` | Live public search is performed before DeepSeek answers time-sensitive external facts. |
| `comparison` | OPPO facts come from Source_B; competitor/current facts come from public search; DeepSeek synthesizes the comparison. |
| `notify` | Notification/lead flow. |
| `blocked` | Unreleased/confidential OPPO requests are stopped before model synthesis. |

## Examples

- `What is LTPO?` -> `direct`
- `Why does OLED show true black?` -> `direct`
- `How should I photograph the aurora?` -> `direct`
- `Which OPPO phone is best for battery life?` -> `recommendation`
- `What is the Find X9 Pro battery capacity?` -> `official`
- `What is the current iPhone 17 price?` -> `current_external`
- `Compare Find X9 Pro with iPhone 17` -> `comparison`
- `What is the leaked Find X10 price?` -> `blocked`

## Important behavior

Direct/general questions do not load Google Sheets at all. This reduces latency and means a temporary Source_B outage does not disable normal DeepSeek conversation.

Source_B is still mandatory for any current or official OPPO-specific fact. The model must not fill missing OPPO facts from memory.

Current competitor/news/market questions require live public search. `BRAVE_SEARCH_API_KEY` enables the existing Brave Search adapter.
