<template>
  <n-modal v-model:show="visible" preset="card" title="Telegram 通知模板" :style="modalStyle" class="custom-modal glass-modal">
    <n-spin :show="loading">
      <n-space vertical :size="14">
        <n-alert type="info" :show-icon="true">
          打开后会直接载入默认模板，可在正文上修改后单独保存。模板支持 MarkdownV2 和下方占位符。
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
                v-model:value="model[item.key]"
                type="textarea"
                :autosize="{ minRows: 8, maxRows: 16 }"
              />
              <div class="template-variable-list">
                <n-tag v-for="name in item.vars" :key="name" size="small" round>
                  {{ formatTemplateVar(name) }}
                </n-tag>
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
import { computed, ref } from 'vue';
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
  useMessage
} from 'naive-ui';

const message = useMessage();
const visible = ref(false);
const loading = ref(false);
const saving = ref(false);

const defaultTemplates = {
  library_new: '{{ media_icon }} {{ title }} {{ notification_title }}\n\n{{ episode_info }}\n{{ media_params }}\n⏰ *时间*: `{{ time }}`\n📝 *剧情*: {{ overview }}\n{{ review_warning }}',
  playback: '{{ action }}\n\n👤 *用户*: `{{ user }}`\n🎬 *媒体*: {{ title }}\n📱 *设备*: `{{ device }}（{{ client }}）`\n🕒 *时间*: `{{ time }}`\n{{ overview }}'
};

const model = ref({ ...defaultTemplates });

const templateOptions = [
  {
    key: 'library_new',
    label: '入库通知',
    vars: ['media_icon', 'title', 'plain_title', 'notification_title', 'episode_info', 'media_params', 'time', 'overview', 'review_warning', 'type', 'tmdb_id']
  },
  {
    key: 'playback',
    label: '播放通知',
    vars: ['action', 'user', 'title', 'plain_title', 'device', 'client', 'time', 'overview']
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

defineExpose({ open });
</script>

<style scoped>
.template-variable-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>