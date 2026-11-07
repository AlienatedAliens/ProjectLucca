"""
Pre-tokenizes canonical Asuka reference stems for Spark-TTS.
Extracts BiCodec global and semantic token IDs and saves them to a PyTorch cache
so that runtime inference incurs zero prompt extraction latency.
"""

import sys
from pathlib import Path
import torch

sys.path.insert(0, r"C:\ProjectLucca\app\Spark-TTS")
from sparktts.models.audio_tokenizer import BiCodecTokenizer

model_dir = Path(r"C:\ProjectLucca\app\Spark-TTS\pretrained_models\Spark-TTS-0.5B")
tokenizer = BiCodecTokenizer(model_dir, device=torch.device("cuda:0"))

stems = {
    "inventor": {
        "wav": Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_023_focused_analytical_in_japanese_they_do_actually.wav"),
        "text": "In Japanese they do actually say when you listen to the Japanese version, you can hear me",
    },
    "companion": {
        "wav": Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_079_focused_analytical_we_re_so_you_know_we_re_batt.wav"),
        "text": "We're so, you know, we're battling these monsters, these angels, and then we need to feed them all.",
    },
    "heroine": {
        "wav": Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_115_anger_arousal_so_it_didn_t_occur_to_them_l.wav"),
        "text": "So it didn't occur to them like, oh, they're going to make no footage.",
    },
    "playful_teasing": {
        "wav": Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_000_focused_analytical_even_the_setting_i_feel_like.wav"),
        "text": "Even the setting, I feel like I should be presenting something.",
    },
}

cache = {}
print("Pre-tokenizing prompt audio stems for Spark-TTS...")
for key, data in stems.items():
    wav_path = data["wav"]
    print(f"Tokenizing {key} -> {wav_path.name}")
    global_token_ids, semantic_token_ids = tokenizer.tokenize(wav_path)
    global_tokens = "".join([f"<|bicodec_global_{i}|>" for i in global_token_ids.squeeze()])
    semantic_tokens = "".join([f"<|bicodec_semantic_{i}|>" for i in semantic_token_ids.squeeze()])
    cache[key] = {
        "prompt_text": data["text"],
        "global_token_ids": global_token_ids.cpu(),
        "semantic_token_ids": semantic_token_ids.cpu(),
        "global_tokens": global_tokens,
        "semantic_tokens": semantic_tokens,
    }

out_file = Path(r"C:\Projects\ProjectLucca\models\tts\spark_prompt_cache.pt")
torch.save(cache, out_file)
print(f"Successfully cached {len(cache)} prompt profiles to {out_file}!")
