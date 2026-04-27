// src/stores/auth.js
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
// import axios from 'axios'; // 预览模式下不需要发请求，先注释掉

export const useAuthStore = defineStore('auth', () => {
  // ★★★ 1. 强行将初始状态设为已登录 ★★★
  const isLoggedIn = ref(true);
  
  // ★★★ 2. 强行塞入一个管理员用户数据 ★★★
  const user = ref({ 
    name: 'UI设计师', 
    is_admin: true, 
    user_type: 'admin',
    allow_unrestricted_subscriptions: true 
  }); 
  
  const systemStatus = ref('logged_in');

  const username = computed(() => {
    return user.value?.name || user.value?.username || '未登录';
  });

  const isAdmin = computed(() => user.value?.is_admin || false);
  
  const userType = computed(() => user.value?.user_type || 'emby_user');

  // ★★★ 3. 拦截检查状态的方法，直接返回成功 ★★★
  async function checkAuthStatus() {
    // 模拟一下网络延迟
    await new Promise(resolve => setTimeout(resolve, 100));
    
    systemStatus.value = 'logged_in';
    isLoggedIn.value = true;
    user.value = { 
      name: 'UI设计师', 
      is_admin: true, 
      user_type: 'admin',
      allow_unrestricted_subscriptions: true 
    };
    return 'logged_in';
  }

  // ★★★ 4. 拦截登录方法，随便输入什么都直接成功 ★★★
  async function login(credentials) {
    await new Promise(resolve => setTimeout(resolve, 300)); // 模拟 loading 动画
    isLoggedIn.value = true;
    user.value = { 
      name: credentials.username || 'UI设计师', 
      is_admin: true, 
      user_type: 'admin',
      allow_unrestricted_subscriptions: true 
    };
  }

  // ★★★ 5. 拦截登出方法 ★★★
  async function logout() {
    isLoggedIn.value = false;
    user.value = {};
    systemStatus.value = 'login_required';
  }

  return {
    isLoggedIn,
    user,
    username, 
    isAdmin,
    userType,
    systemStatus,
    checkAuthStatus,
    login,
    logout
  };
});