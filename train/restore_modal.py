"""QLoRA fine-tune of ALLaM-7B-Instruct as the Muhaqiq restorer, on a Modal A10G (24 GB).
Run:  modal run train/restore_modal.py          (~45-90 min; adapter pushed to muhaqiq/muhaqiq-allam-restorer)
Needs: modal secret `huggingface` with HF_TOKEN (write), and the ALLaM licence accepted on its model page.
Docs: TRL SFTTrainer https://huggingface.co/docs/trl/sft_trainer · PEFT LoRA https://huggingface.co/docs/peft/package_reference/lora
      Modal GPUs https://modal.com/docs/guide/gpu
"""
import modal

BASE = "ALLaM-AI/ALLaM-7B-Instruct-preview"
OUT = "muhaqiq/muhaqiq-allam-restorer"
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch", "transformers", "peft", "trl", "bitsandbytes", "datasets", "accelerate", "huggingface_hub"))
app = modal.App("muhaqiq-restorer-train", image=image)

@app.function(gpu="A10G", timeout=4 * 3600, secrets=[modal.Secret.from_name("huggingface")])
def train(smoke: bool = False):
    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    ds = load_dataset("muhaqiq/restore-data")["train"]
    if smoke: ds = ds.select(range(64))
    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE, device_map="auto",
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16))
    model = prepare_model_for_kbit_training(model)

    args = SFTConfig(output_dir="/tmp/restorer", num_train_epochs=1, per_device_train_batch_size=4, gradient_accumulation_steps=4,
                     learning_rate=2e-4, lr_scheduler_type="cosine", warmup_ratio=0.03, bf16=True, logging_steps=10,
                     save_strategy="steps", save_steps=200, max_length=512, report_to="none",
                     push_to_hub=not smoke, hub_model_id=OUT, hub_private_repo=False)
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = SFTTrainer(model=model, args=args, train_dataset=ds, processing_class=tok, peft_config=lora)
    trainer.train()
    if not smoke: trainer.push_to_hub(); tok.push_to_hub(OUT)
    return trainer.state.log_history[-1]

@app.local_entrypoint()
def main(smoke: bool = False):
    print(train.remote(smoke))
