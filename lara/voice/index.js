'use strict';
// Provider contracts keep speech services replaceable and outside methodology.
class SpeechToTextProvider { async transcribe(_audio, _options={}) { throw new Error('SpeechToTextProvider.transcribe must be implemented'); } }
class TextToSpeechProvider { async synthesize(_text, _options={}) { throw new Error('TextToSpeechProvider.synthesize must be implemented'); } }
module.exports={SpeechToTextProvider,TextToSpeechProvider};
