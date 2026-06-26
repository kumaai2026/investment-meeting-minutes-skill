# Runtime Readiness Guide

Use this file before running audio transcription, Dify service smoke tests, or production-like meeting imports.

## Runtime Rule

Runtime execution must not download models, install packages, or silently switch engines. Preparation is a separate deployment step.

Allowed during a live meeting job:

- Use already-installed Python packages.
- Use already-cached ASR models.
- Use already-configured local services.
- Continue from user-provided text when audio transcription cannot run, while reporting the missing capability.

Not allowed during a live meeting job:

- Download SenseVoice models.
- Install Python packages on demand.
- Switch from SenseVoice to Whisper or another ASR.
- Estimate timestamps from cleaned-note text position.
- Pretend Word, Dify, or Google Drive sync succeeded when the step failed.

## Readiness Profiles

Use the narrowest readiness profile that matches the next expensive step:

```bash
python3 scripts/check_investment_workflow_health.py --profile asr --strict
python3 scripts/check_investment_workflow_health.py --profile export
python3 scripts/check_investment_workflow_health.py --profile dify
python3 scripts/check_investment_workflow_health.py --profile full --strict
```

Profile intent:

- `asr`: check only local transcription prerequisites and the SenseVoice service/cache. Use before audio transcription.
- `export`: check local archive/export paths, Word dependency, and rclone availability/log status. Use before final Markdown + Word export.
- `dify`: check Dify, review/export bridges, workflow output contract, sync mapping, and access-control plumbing. Use before production-like Dify imports.
- `full`: run the broad machine health audit. Use for deployment validation, not for every meeting note.

Strict ASR/full mode should fail if required local runtime assets are missing:

- `funasr`
- `modelscope`
- `soundfile`
- `librosa`
- `docx`
- local SenseVoice model cache
- the model cache path reported by the running SenseVoice service
- review/export bridge health endpoints
- SenseVoice transcription bridge health endpoint
- Obsidian archive/output paths

The maintained audio workflow is plain SenseVoice. Extra ASR comparison, segmentation, or speaker-identification paths are outside the current reusable skill contract.

For a narrow ASR cache check:

```bash
python3 scripts/transcribe_audio.py --check-model-cache
```

This command only reports cache status. It must not download missing files.

## Deployment Preparation

If strict mode reports missing packages or models, fix the deployment before live use. Any download or package installation belongs in a manual deployment/preparation step, not inside the meeting-processing run.

Record the final model cache path and Python environment path in the local service configuration or LaunchAgent. Do not vendor model weights, virtualenvs, Python wheels, private tokens, or local caches into the reusable skill package.

The skill package should contain:

- rules and prompts
- deterministic scripts
- references and templates
- regression samples
- health checks
- optional example manifests without secrets

The deployment environment should contain:

- downloaded ASR model caches
- Python virtual environments
- platform-specific binaries
- private Dify, rclone, and Google Drive configuration
- local logs and runtime state

If a runtime asset manifest is needed, generate it from the deployment environment and keep it outside the reusable skill package unless it is a redacted example.
