import torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_ID = "aiplanet/LuxLlama"

# ----------------------------
# Load tokenizer
# ----------------------------
print("[LuxLLaMA] Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_ID,
    trust_remote_code=True
)

# ----------------------------
# Load model on GPU
# ----------------------------
print("[LuxLLaMA] Loading model on GPU (fp16)...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="cuda",
    trust_remote_code=True
)

model.eval()
print("[LuxLLaMA] Model loaded on", torch.cuda.get_device_name(0))

# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI(title="LuxLLaMA GPU Server")

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 256

class GenerateResponse(BaseModel):
    text: str


@app.post("/generate")
def generate(req: GenerateRequest):
    prompt = req.prompt.strip()
    if not prompt:
        return {"text": ""}

    # Tokenize
    inputs = tokenizer(prompt, return_tensors="pt")

    # 🔑 MOVE INPUTS TO GPU
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=req.max_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            eos_token_id=tokenizer.eos_token_id,
        )

    # 🔑 Decode ONLY new tokens
    generated_ids = outputs[0][inputs["input_ids"].shape[-1]:]
    text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

    return {"text": text}