class AudioCapture extends AudioWorkletProcessor
{
    constructor()
    {
        super();
        this.size = Math.round(sampleRate / 10);
        this.buf = new Int16Array(this.size);
        this.pos = 0;
    }

    process(inputs)
    {
        const ch = inputs[0][0] // mono channel
        if (ch)
        {
            for (let i = 0; i < ch.length; i++)
            {
                const s = Math.max(-1, Math.min(1, ch[i]));
                // Convenient conversion from float32 to int16 from here 
                // https://stackoverflow.com/questions/33738873/float32-to-int16-javascript-web-audio-api
                this.buf[this.pos] = s < 0 ? s * 0x8000 : s * 0x7ffff;
                this.pos++;
                if (this.pos == this.size)
                {
                    this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
                    this.buf = new Int16Array(this.size);
                    this.pos = 0;
                }
            }
        }
        return true;
    }
}

registerProcessor("audio-capture", AudioCapture)