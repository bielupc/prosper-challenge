# Prosper Challenge Solution

## Initial Notes
- HTTPMethod was added to Python's standard library http module in Python 3.11. It does not exist in Python 3.10. Updated.

**Tasks**
- Test bot
- Read how bot works
- Define database and schema
- Create a backend for the EHR endpoints
- Frontend with webhook to see live changes
- Secure sentitive data
- Add tools to call my backend
- Change system prompt to guide the agent through patient identification → registration → appointment scheduling/cancellation using prompt engineering.
- Extra features

**Pipeline**
- LocalSmartTurnAnalyzerV3 - Detect when the user stops speaking
- SileroVADAnalyzer - Detect if there is speech in the audio
- WebRTC - Protocol to share voice straming with peers
- transport.input() is the raw user input via WebRTC
- transport.output() is the generated audo the user listens to

- run_bot
  - Initializes STT, TTS, OpenAI LLM
  - LLMcontext is the object holding the conversation history
  - The LLMContextAggregatorPair configures the conversation flow with turn logic and batch messages user-llm
  - RTVIProcessor is the browser UI
  - Pipeline definition
    - User input -> STT -> user_aggregator -> llm -> tts -> Agent output -> assistant_aggregator
  - Pipeline task stores metrics and outputs to the rtvi
  - Event handles on connect and disconnect greet (add message -> enqueue a trigger to speak) or cleanup
  - PipelineRunner runs the pipeline

- bot
  - Create WebRTC tranport
  - Simple Voice Activity Detector for the initialization, not in the pipeline
  - Run the bot

- Main runs pipecat main which runs the standard bot function

## Brainstorming
- FastAPI backend w/ Postgresql
- Vite frontend with a simple SSE to display DB information in realtime
- Dockerized 
- (name, DOB) must be tool arguments
- Validate tool arguments server side
- Find patient returns a patient identifier for followup tool calls
- The patient id in followup calls should not be LLM generated
- list-availability readonly
- Log all tool calls

## Improvements
Latency, Reliability, Evaluation
- How can I prevent the user claiming to be someone else?
- IP + session tool call rate limit on transport layer to avoid ennumerating patients (find_patient)
- Fallback for reliability
- Eval?