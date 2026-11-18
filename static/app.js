const start_btn = document.getElementById("start");
const stop_btn = document.getElementById("stop");
const status_field = document.getElementById("status");

// uint32 sequence num + float64 timestamp from phone
const HEADER_BYTES = 12;
let ctx, audio_stream, node, ws, wakeLock;
let seq = 0;
let running = false;

start_btn.onclick = async () =>
{
    start_btn.disabled = true;
    try
    {
        audio_stream = await navigator.mediaDevices.getUserMedia(
            {
                audio:
                {
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false,
                },
            }
        );

        ctx = new AudioContext();
        ctx.resume() // Mobile browser fix
        await ctx.audioWorklet.addModule("/static/audio-worklet.js");

        ws = new WebSocket(`wss://${location.host}/ws`);
        ws.binaryType = "arraybuffer";
        await new Promise((resolve, reject) =>
        {
            ws.onopen = resolve;
            ws.onerror = () => reject(new Error("Websocket failed"))
        }
        );
        running = true;

        const track = audio_stream.getAudioTracks()[0];
        ws.send(JSON.stringify(
            {
                type: "start",
                sampleRate: ctx.sampleRate,
                trackSettings: track.getSettings(),
                userAgent: navigator.userAgent,
                clientTime: Date.now(),
            }
        ));

        const source = ctx.createMediaStreamSource(audio_stream);
        node = new AudioWorkletNode(ctx, "audio-capture");
        node.port.onmessage = (e) => sendChunk(e.data);
        source.connect(node);
        node.connect(ctx.destination);

        ws.onclose = () => stop("Disconnected");

        if ("wakeLock" in navigator)
        {
            // Keep the screen on.
            wakeLock = await navigator.wakeLock.request("screen").catch(() => null);
        }

        stop_btn.disabled = false;
    }
    catch (err)
    {
        status_field.textContent = `Error: ${err.message ?? err}`
        cleanup();
        start_btn.disabled = false;
    }
};

stop_btn.onclick = () => { stop("Stopped"); }

function sendChunk(chunk)
{
    // Always increments to keep track of chunks the server has missed
    const s = seq++;
    if(!ws || ws.readyState !== WebSocket.OPEN) return;

    const packet = new ArrayBuffer(HEADER_BYTES + chunk.byteLength);
    const view = new DataView(packet);
    // Add packet index and time
    view.setUint32(0, s, true);
    view.setFloat64(4, performance.timeOrigin + performance.now(), true);
    new Uint8Array(packet, HEADER_BYTES).set(new Uint8Array(chunk));
    ws.send(packet);
}

function stop(reason)
{
    if (!running) return;
    running = false;
    if (ws && ws.readyState === WebSocket.OPEN)
    {
        ws.onclose = null;
        ws.send(JSON.stringify({ type: "stop", clientTime: Date.now()}));
        ws.close();
    }
    if (reason)
    {
        status_field.textContent = reason
    }
    cleanup();
    stop_btn.disabled = true;
    start_btn.disabled = false;
}

function cleanup()
{
    node?.disconnect();
    audio_stream?.getAudioTracks().forEach((t) => t.stop());
    ctx?.close();
    wakeLock?.release();
    node = audio_stream = ctx = wakeLock = null;
}