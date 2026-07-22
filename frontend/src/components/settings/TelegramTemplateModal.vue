<template>
  <n-modal v-model:show="visible" preset="card" title="Telegram 通知模板" :style="modalStyle" class="custom-modal glass-modal">
    <n-spin :show="loading">
      <n-space vertical :size="14">
        <n-alert type="info" :show-icon="true">
          打开后会直接载入默认模板，可在正文上修改后单独保存。<br/>
          模板支持 MarkdownV2。<b>点击下方变量标签，可直接将其插入到文本框光标处。</b>
        </n-alert>
        <n-tabs type="line" animated>
          <n-tab-pane
            v-for="item in templateOptions"
            :key="item.key"
            :name="item.key"
            :tab="item.label"
          >
            <n-space vertical :size="10">
              <n-input
                :id="`template-input-${item.key}`"
                v-model:value="model[item.key]"
                type="textarea"
                :autosize="{ minRows: 8, maxRows: 16 }"
                placeholder="在此编辑您的通知模板..."
              />
              <div class="template-variable-list">
                <n-tooltip v-for="v in item.vars" :key="v.name" placement="top" trigger="hover">
                  <template #trigger>
                    <n-tag 
                      size="small" 
                      round 
                      class="clickable-tag n-tag-cyan"
                      @click="insertVariable(item.key, v.name)"
                    >
                      {{ formatTemplateVar(v.name) }}
                    </n-tag>
                  </template>
                  {{ v.desc }}
                </n-tooltip>
              </div>
              <n-button size="small" quaternary @click="resetTemplate(item.key)">
                恢复默认
              </n-button>
            </n-space>
          </n-tab-pane>
        </n-tabs>
      </n-space>
    </n-spin>
    <template #footer>
      <n-space justify="end">
        <n-button @click="visible = false">关闭</n-button>
        <n-button type="primary" :loading="saving" @click="saveTemplates">保存模板</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, ref, nextTick } from 'vue';
import axios from 'axios';
import {
  NAlert,
  NButton,
  NInput,
  NModal,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NTooltip,
  useMessage
} from 'naive-ui';

const message = useMessage();
const visible = ref(false);
const loading = ref(false);
const saving = ref(false);

const defaultTemplates = {
  library_new: '{{ media_icon }} {{ title }} {{ notification_title }}\n\n{{ episode_info }}\n{{ media_params }}\n⏰ *时间*: `{{ time }}`\n📝 *剧情*: {{ overview }}\n{{ review_warning }}',
  playback: '{{ action }}\n\n👤 *用户*: `{{ user }}`\n🎬 *媒体*: {{ title }}\n{{ progress }}\n📱 *设备*: `{{ device }}（{{ client }}）`\n🌐 *地址*: {{ ip }}\n🕒 *时间*: `{{ time }}`\n{{ overview }}'
};

const model = ref({ ...defaultTemplates });

// 定义变量词典及其中文注释
const templateOptions = [
  {
    key: 'library_new',
    label: '入库通知',
    vars: [
      { name: 'media_icon', desc: '媒体图标 (🎬电影 / 📺剧集)' },
      { name: 'title', desc: '带有 Markdown 加粗的标题' },
      { name: 'plain_title', desc: '纯文本标题 (无格式)' },
      { name: 'notification_title', desc: '通知动作 (如: ✨ 入库成功)' },
      { name: 'episode_info', desc: '季集范围信息 (仅剧集有)' },
      { name: 'media_params', desc: '画质、音轨、字幕、体积等参数' },
      { name: 'time', desc: '当前系统时间' },
      { name: 'overview', desc: '剧情简介' },
      { name: 'review_warning', desc: '待复核警告提示' },
      { name: 'type', desc: '媒体类型 (Movie/Series/Episode)' },
      { name: 'tmdb_id', desc: 'TMDb 编号' }
    ]
  },
  {
    key: 'playback',
    label: '播放通知',
    vars: [
      { name: 'action', desc: '播放动作 (▶️ 开始播放 / ⏸ 暂停 等)' },
      { name: 'user', desc: '播放用户的名称' },
      { name: 'title', desc: '带有 Markdown 加粗的媒体标题' },
      { name: 'plain_title', desc: '纯文本标题 (无格式)' },
      { name: 'progress', desc: '播放进度 (如: 00:15:30 / 01:20:00)' },
      { name: 'device', desc: '播放设备 (如: Apple TV)' },
      { name: 'client', desc: '播放客户端 (如: Emby for tvOS)' },
      { name: 'ip', desc: '用户 IP 及地理位置' },
      { name: 'time', desc: '当前系统时间' },
      { name: 'overview', desc: '剧情简介' }
    ]
  }
];

const modalStyle = computed(() => ({
  width: window.innerWidth <= 768 ? 'calc(100vw - 24px)' : '760px',
  maxWidth: 'calc(100vw - 24px)'
}));

const normalizeTemplates = (templates) => ({
  ...defaultTemplates,
  ...(templates && typeof templates === 'object' && !Array.isArray(templates) ? templates : {})
});

const fetchTemplates = async () => {
  loading.value = true;
  try {
    const response = await axios.get('/api/telegram/templates');
    model.value = normalizeTemplates(response.data);
  } catch (error) {
    message.error(error.response?.data?.error || '读取 Telegram 通知模板失败');
  } finally {
    loading.value = false;
  }
};

const open = async () => {
  visible.value = true;
  await fetchTemplates();
};

const resetTemplate = (key) => {
  model.value[key] = defaultTemplates[key] || '';
};

const saveTemplates = async () => {
  saving.value = true;
  try {
    const response = await axios.post('/api/telegram/templates', {
      templates: normalizeTemplates(model.value)
    });
    model.value = normalizeTemplates(response.data?.templates);
    message.success(response.data?.message || 'Telegram 通知模板已保存');
    visible.value = false;
  } catch (error) {
    message.error(error.response?.data?.error || '保存 Telegram 通知模板失败');
  } finally {
    saving.value = false;
  }
};

const formatTemplateVar = (name) => `{{ ${name} }}`;

// 核心功能：点击 Tag 将变量插入到输入框的光标位置
const insertVariable = (key, varName) => {
  const variableStr = formatTemplateVar(varName);
  const container = document.getElementById(`template-input-${key}`);
  
  if (container) {
    // Naive UI 的 n-input 内部包装了实际的 textarea 元素
    const textarea = container.querySelector('textarea');
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const text = model.value[key];
      
      // 拼接字符串
      model.value[key] = text.substring(0, start) + variableStr + text.substring(end);
      
      // 保持焦点并将光标移动到插入的变量之后
      nextTick(() => {
        textarea.focus();
        const newCursorPos = start + variableStr.length;
        textarea.setSelectionRange(newCursorPos, newCursorPos);
      });
      return;
    }
  }
  // 兜底策略：如果没有找到光标位置，则追加到最后
  model.value[key] += variableStr;
};

defineExpose({ open });
</script>

<style scoped>
.template-variable-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 增加 Tag 点击的交互感 */
.clickable-tag {
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}
.clickable-tag:hover {
  filter: brightness(0.9);
  transform: scale(1.05);
}
.clickable-tag:active {
  transform: scale(0.95);
}
</style>