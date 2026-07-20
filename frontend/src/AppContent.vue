<!-- src/AppContent.vue -->
<template>
  <MainLayout 
    v-if="showMainLayout"
    :is-dark="isDarkTheme" 
    :task-status="backgroundTaskStatus"
    @update:is-dark="handleModeChange"
  />
  <n-modal
    v-model:show="serviceAuthorizationVisible"
    preset="card"
    title="Emby 服务授权"
    :style="{ width: 'min(480px, calc(100vw - 24px))' }"
    :mask-closable="serviceAuthorized"
    :close-on-esc="serviceAuthorized"
    :closable="serviceAuthorized"
  >
    <n-alert type="warning" :show-icon="true" style="margin-bottom: 16px;">
      后台任务需要 Emby 管理员授权。账号密码仅用于本次认证，不会保存。
    </n-alert>
    <n-form ref="serviceAuthorizationFormRef" :model="serviceAuthorizationForm" :rules="serviceAuthorizationRules">
      <n-form-item label="Emby URL" path="url">
        <n-input v-model:value="serviceAuthorizationForm.url" placeholder="http://localhost:8096" />
      </n-form-item>
      <n-form-item label="管理员用户名" path="username">
        <n-input v-model:value="serviceAuthorizationForm.username" autocomplete="username" />
      </n-form-item>
      <n-form-item label="管理员密码" path="password">
        <n-input
          v-model:value="serviceAuthorizationForm.password"
          type="password"
          show-password-on="mousedown"
          autocomplete="current-password"
          placeholder="无密码账号可留空"
          @keydown.enter="submitServiceAuthorization"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button v-if="serviceAuthorized" @click="serviceAuthorizationVisible = false">取消</n-button>
        <n-button type="primary" :loading="serviceAuthorizationSubmitting" @click="submitServiceAuthorization">
          授权
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <div v-if="!showMainLayout" class="fullscreen-container">
    <router-view />
  </div>
  <div v-if="!isReady" class="fullscreen-container loader-container">
    <n-spin size="large" />
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import {
  NSpin, NModal, NForm, NFormItem,
  NInput, NButton, NAlert, NSpace
} from 'naive-ui';
import { useAuthStore } from './stores/auth';
import MainLayout from './MainLayout.vue';
import axios from 'axios';

const route = useRoute();
const authStore = useAuthStore();
const showMainLayout = computed(() => !route.meta.public);

const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');
const isReady = ref(false);
const backgroundTaskStatus = ref({ is_running: false, current_action: '空闲' });
let statusIntervalId = null;
const serviceAuthorized = ref(true);
const serviceAuthorizationVisible = ref(false);
const serviceAuthorizationSubmitting = ref(false);
const serviceAuthorizationFormRef = ref(null);
const serviceAuthorizationForm = ref({ url: '', username: '', password: '' });
const serviceAuthorizationRules = {
  url: { required: true, message: '请输入 Emby URL', trigger: 'blur' },
  username: { required: true, message: '请输入管理员用户名', trigger: 'blur' },
};
const app = document.getElementById('app');

const getThemeOverrides = (isDark) => {
  const textColor = 'rgba(255, 255, 255, 0.95)';
  const textColor2 = 'rgba(255, 255, 255, 0.75)';
  const inputBg = 'rgba(255, 255, 255, 0.05)';
  const inputBgActive = 'rgba(255, 255, 255, 0.1)';
  const borderColor = 'rgba(255, 255, 255, 0.15)';
  
  return {
    common: {
      primaryColor: '#8a2be2',
      primaryColorHover: '#9b4dec',
      textColor1: textColor,
      textColor2: textColor2,
      textColor3: 'rgba(255, 255, 255, 0.5)',
      dividerColor: borderColor,
      bodyColor: 'transparent',
      cardColor: 'transparent',
      modalColor: isDark ? 'rgba(20, 25, 35, 0.9)' : 'rgba(0, 0, 0, 0.6)',
      popoverColor: isDark ? 'rgba(20, 25, 35, 0.9)' : 'rgba(0, 0, 0, 0.6)',
    },
    Card: { color: 'transparent', borderColor: 'transparent' },
    Input: {
      color: inputBg, colorFocus: inputBgActive,
      border: `1px solid ${borderColor}`, borderFocus: `1px solid #8a2be2`,
      textColor: textColor, borderRadius: '8px'
    },
    Select: {
      peers: {
        InternalSelection: {
          color: inputBg, colorActive: inputBgActive,
          border: `1px solid ${borderColor}`, borderActive: `1px solid #8a2be2`,
          textColor: textColor, borderRadius: '8px'
        }
      }
    },
    Button: { textColor: textColor, borderRadius: '8px' },
    Menu: {
      itemColorHover: inputBg, itemColorActive: inputBgActive,
      itemTextColor: textColor2, itemTextColorActive: textColor,
      itemIconColor: textColor2, itemIconColorActive: textColor,
      borderRadius: '12px'
    }
  };
};

const applyTheme = (isDark) => {
  const root = document.documentElement;
  app.dispatchEvent(new CustomEvent('update-naive-theme', { detail: getThemeOverrides(isDark) }));
  root.classList.remove('dark', 'light');
  root.classList.add(isDark ? 'dark' : 'light'); 
};

const handleModeChange = (isDark) => {
  isDarkTheme.value = isDark;
  localStorage.setItem('isDark', String(isDark));
  app.dispatchEvent(new CustomEvent('update-dark-mode', { detail: isDark }));
};

watch(isDarkTheme, (isDark) => { applyTheme(isDark); }, { deep: true });

const checkServiceAuthorization = async () => {
  if (!authStore.isLoggedIn) return;
  try {
    const response = await axios.get('/api/auth/service_status');
    serviceAuthorized.value = !!response.data.authorized;
    serviceAuthorizationForm.value.url = response.data.url || '';
    if (!serviceAuthorized.value) serviceAuthorizationVisible.value = true;
  } catch (error) {
    console.error('检查 Emby 服务授权失败:', error);
  }
};

const openServiceAuthorization = () => {
  serviceAuthorizationForm.value.username = '';
  serviceAuthorizationForm.value.password = '';
  serviceAuthorizationVisible.value = true;
};

const submitServiceAuthorization = async () => {
  try {
    await serviceAuthorizationFormRef.value?.validate();
  } catch {
    return;
  }
  serviceAuthorizationSubmitting.value = true;
  try {
    const response = await axios.post('/api/auth/reauthorize', serviceAuthorizationForm.value);
    const authorization = response.data.authorization || {};
    serviceAuthorized.value = true;
    serviceAuthorizationVisible.value = false;
    serviceAuthorizationForm.value.password = '';
    message.success(response.data.message || 'Emby 服务授权成功');
    window.dispatchEvent(new CustomEvent('etk-emby-authorization-updated', { detail: authorization }));
  } catch (error) {
    message.error(error.response?.data?.message || 'Emby 服务授权失败');
  } finally {
    serviceAuthorizationSubmitting.value = false;
  }
};

watch(() => authStore.isLoggedIn, (isLoggedIn) => {
  if (isLoggedIn) {
    if (!statusIntervalId) {
      const fetchStatus = async () => {
        try {
          const response = await axios.get('/api/status');
          backgroundTaskStatus.value = response.data;
        } catch (error) {}
      };
      fetchStatus();
      statusIntervalId = setInterval(fetchStatus, 2000);
      checkServiceAuthorization();
    }
  } else {
    if (statusIntervalId) { clearInterval(statusIntervalId); statusIntervalId = null; }
  }
}, { immediate: true });

onMounted(() => {
  window.addEventListener('etk-open-emby-authorization', openServiceAuthorization);
  applyTheme(isDarkTheme.value);
  isReady.value = true;
});

onBeforeUnmount(() => {
  if (statusIntervalId) clearInterval(statusIntervalId); 
  window.removeEventListener('etk-open-emby-authorization', openServiceAuthorization);
});
</script>

<style scoped>
.loader-container { position: absolute; top: 0; left: 0; z-index: 9999; background: transparent; backdrop-filter: blur(20px); }
</style>