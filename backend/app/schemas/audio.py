from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class AudioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    meeting_id: int
    original_name: str
    size_bytes: int
    created_at: datetime
    status: Literal["AWAITING_TRANSCRIPTION", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"] = "AWAITING_TRANSCRIPTION"
    transcript: str | None = None
    input_id: int | None = None
    error_code: str | None = None
    message: str = "录音已保存，等待接入转写服务。可先提供会议文本继续处理。"

    @model_validator(mode='after')
    def status_message(self):
        messages = {'QUEUED': '录音已保存，正在等待转写。', 'RUNNING': '正在本机转写录音。',
                    'SUCCEEDED': '转写已完成，已提交会议分析。', 'FAILED': '转写处理失败，可重试或改用会议文本。'}
        errors = {'ASR_MODEL_MISSING': '本地转写模型未下载，请先运行模型下载脚本。',
                  'ASR_NO_SPEECH': '没有识别到有效语音，请换一段清晰录音。',
                  'ASR_TOO_LONG': '录音或转写文本超过演示处理上限，请使用较短录音。',
                  'ASR_INPUT_CHANGED': '会议已有更新内容，本次转写未覆盖新版本；可复制转写文本人工核对。',
                  'ASR_PERMISSION_CHANGED': '提交人的会议管理权限已改变，未自动提交分析。'}
        self.message = errors.get(self.error_code, messages.get(self.status, self.message))
        return self
