/* ══════════════════════════════════════════════════════════════════════════
   gemini-live.js — Gemini Live voice-to-voice integration

   Uses Gemini Live API for bidirectional audio streaming.
   The candidate speaks directly to Gemini, which transcribes, evaluates,
   and responds in real time. Separates audio handling from REST logic.

   Flow:
     1. Backend provides the question text
     2. Frontend opens Gemini Live WebSocket with the question as context
     3. Candidate speaks → Gemini Live transcribes + responds
     4. On turn end, we extract transcript + score from Gemini's response
     5. Submit to backend via /session/submit-transcript
     6. Backend returns next question → repeat
   ══════════════════════════════════════════════════════════════════════════ */

const GEMINI_API_KEY = ''; // Set from .env or config — user provides this
const GEMINI_LIVE_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent';

let geminiWs = null;
let geminiAudioCtx = null;
let geminiStream = null;
let isGeminiActive = false;

/**
 * Start a Gemini Live session for the given interview question.
 * Returns a promise that resolves when Gemini has spoken the question
 * and is ready for the candidate's answer.
 */
async function startGeminiLive(question, role, skill, onTranscript, onComplete) {
  if (!GEMINI_API_KEY) {
    throw new Error('Gemini API key not configured. Set GEMINI_API_KEY in gemini-live.js');
  }

  await stopGeminiLive();

  geminiAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });

  // Build the system prompt
  const systemPrompt = `You are an expert technical interviewer conducting a voice interview for a ${role} role.
The current skill being tested is: ${skill}.
You are speaking to the candidate directly via voice. 

CRITICAL RULES:
- Start by reading this question aloud: "${question}"
- After reading the question, listen to the candidate's spoken answer
- After the candidate finishes, you MUST respond with ONLY a JSON object in this format:
  {"transcript": "<what the candidate said>", "score": <1-10>, "feedback": "<1-2 sentence evaluation>"}
- Do not add any other text before or after the JSON
- Do not ask follow-up questions yourself — just evaluate and output JSON`;

  const url = `${GEMINI_LIVE_URL}?key=${GEMINI_API_KEY}`;

  geminiWs = new WebSocket(url);
  geminiWs.binaryType = 'arraybuffer';

  return new Promise((resolve, reject) => {
    geminiWs.onopen = () => {
      // Send setup configuration
      geminiWs.send(JSON.stringify({
        setup: {
          model: 'models/gemini-2.0-flash-live-001',
          generation_config: {
            response_modalities: ['AUDIO'],
            speech_config: {
              voice_config: { prebuilt_voice_config: { voice_name: 'Puck' } }
            }
          },
          system_instruction: {
            parts: [{ text: systemPrompt }]
          }
        }
      }));

      isGeminiActive = true;
      resolve();
    };

    geminiWs.onmessage = async (event) => {
      let data;
      if (event.data instanceof ArrayBuffer) {
        // Audio data from Gemini — play it
        const buffer = await geminiAudioCtx.decodeAudioData(event.data.slice());
        const source = geminiAudioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(geminiAudioCtx.destination);
        source.start();
      } else {
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }

        // Check for text/transcript from Gemini
        if (data.serverContent?.modelTurn?.parts) {
          for (const part of data.serverContent.modelTurn.parts) {
            if (part.text) {
              // Try to extract JSON evaluation
              try {
                const jsonMatch = part.text.match(/\{[\s\S]*\}/);
                if (jsonMatch) {
                  const result = JSON.parse(jsonMatch[0]);
                  if (result.transcript && result.score) {
                    onTranscript(result);
                    if (onComplete) onComplete(result);
                  }
                }
              } catch {
                // Non-JSON text — might be Gemini's spoken response (already handled as audio)
              }
            }
          }
        }

        // Check if Gemini finished speaking
        if (data.serverContent?.turnComplete) {
          isGeminiActive = false;
        }
      }
    };

    geminiWs.onerror = (err) => {
      console.error('Gemini Live WS error:', err);
      reject(err);
    };

    geminiWs.onclose = () => {
      isGeminiActive = false;
    };
  });
}

/**
 * Start capturing microphone audio and sending it to Gemini Live.
 */
async function startGeminiMic() {
  if (!geminiWs || !isGeminiActive) return;

  geminiStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: 16000,
      echoCancellation: true,
      noiseSuppression: true,
    }
  });

  const source = geminiAudioCtx.createMediaStreamSource(geminiStream);
  const processor = geminiAudioCtx.createScriptProcessor(4096, 1, 1);

  source.connect(processor);
  processor.connect(geminiAudioCtx.destination);

  processor.onaudioprocess = (e) => {
    if (geminiWs && geminiWs.readyState === WebSocket.OPEN && isGeminiActive) {
      const inputData = e.inputBuffer.getChannelData(0);
      // Convert Float32 to Int16 PCM
      const pcmData = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        pcmData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
      }

      geminiWs.send(JSON.stringify({
        realtimeInput: {
          mediaChunks: [{
            mimeType: 'audio/pcm;rate=16000',
            data: btoa(String.fromCharCode(...new Uint8Array(pcmData.buffer)))
          }]
        }
      }));
    }
  };
}

/**
 * Stop microphone and Gemini Live connection.
 */
async function stopGeminiMic() {
  if (geminiStream) {
    geminiStream.getTracks().forEach(t => t.stop());
    geminiStream = null;
  }
}

async function stopGeminiLive() {
  await stopGeminiMic();
  if (geminiWs) {
    geminiWs.close();
    geminiWs = null;
  }
  if (geminiAudioCtx) {
    await geminiAudioCtx.close();
    geminiAudioCtx = null;
  }
  isGeminiActive = false;
}
