"""ALLaM-7B on a Modal A10G, two routes:
  POST /restore {"span","label"}  -> {"canonical","reference"}   (LoRA adapter = the fine-tuned restorer)
  POST /chat    {"prompt"}        -> {"text"}                    (base model, adapter off: level classification, notes)
Deploy: modal deploy api/llm_modal.py   · URL printed as https://<you>--muhaqiq-llm-web.modal.run
Docs: https://modal.com/docs/guide/gpu · https://huggingface.co/docs/peft/package_reference/peft_model
"""
import modal

BASE = "ALLaM-AI/ALLaM-7B-Instruct-preview"
ADAPTER = "muhaqiq/muhaqiq-allam-restorer"
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch", "transformers", "peft", "bitsandbytes", "accelerate", "huggingface_hub", "fastapi[standard]",
                      "sentencepiece", "tiktoken", "protobuf"))
app = modal.App("muhaqiq-llm", image=image)

PROMPT = ("النص التالي اقتباس من {kind} كما ورد في إجابة روبوت دردشة، وقد يكون محرَّفًا أو ناقصًا. "
          "أعد اللفظ الصحيح كاملًا كما هو في المصدر، بصيغة JSON بالمفتاحين canonical و reference. "
          "إن لم تكن متأكدًا فاجعل canonical فارغًا.\nالنص: {span}\nJSON:")
KIND = {"AYAH": "القرآن الكريم", "MATN": "الحديث النبوي"}

@app.cls(gpu="A10G", scaledown_window=600, secrets=[modal.Secret.from_name("huggingface")])
@modal.concurrent(max_inputs=4)
class LLM:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        from peft import PeftModel
        self.tok = AutoTokenizer.from_pretrained(BASE)
        base = AutoModelForCausalLM.from_pretrained(BASE, device_map="auto",
                 quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16))
        try: self.model = PeftModel.from_pretrained(base, ADAPTER); self.has_adapter = True
        except Exception as e: print("no adapter yet:", e); self.model = base; self.has_adapter = False

    def generate(self, prompt, adapter):
        import torch
        text = self.tok.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True, tokenize=False)
        enc = self.tok(text, return_tensors="pt", add_special_tokens=False).to("cuda")     # template already added BOS
        ctx = self.model.disable_adapter() if (self.has_adapter and not adapter) else torch.no_grad()
        with ctx, torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=200, do_sample=False)
        return self.tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    @modal.asgi_app()
    def web(self):
        import json, re
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        api = FastAPI(title="Muhaqiq LLM")
        api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

        @api.post("/restore")
        def restore(body: dict):
            text = self.generate(PROMPT.format(kind=KIND.get(body.get("label"), "القرآن أو الحديث"), span=body["span"]), adapter=True)
            m = re.search(r"\{.*\}", text, re.S)
            try: return json.loads(m.group()) if m else {"canonical": "", "reference": ""}
            except json.JSONDecodeError: return {"canonical": "", "reference": "", "raw": text}

        @api.post("/chat")
        def chat(body: dict):
            return {"text": self.generate(body["prompt"], adapter=False)}
        return api
