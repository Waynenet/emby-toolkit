<!-- src/components/settings/GeneralSettingsPage.vue -->
<template>
  <n-layout content-style="padding: 16px; max-width: 1600px; margin: 0 auto;">
    <n-space vertical :size="16" style="margin-top: 5px;">
      
      <div v-if="configModel">
        <n-form
          ref="formRef"
          :rules="formRules"
          @submit.prevent="save"
          label-placement="top"
          :model="configModel"
        >
          <n-tabs type="line" animated pane-style="padding: 16px 0 0 0; box-sizing: border-box;">
            
            <!-- ================== 标签页 1: 通用设置 ================== -->
            <n-tab-pane name="general" tab="通用设置">
              <n-grid cols="1 l:3" :x-gap="16" :y-gap="16" responsive="screen">
                
                <!-- 第一列: 基础设置 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">基础设置</span></template>
                    <n-grid cols="1 s:2" :x-gap="12" :y-gap="8" responsive="screen">
                      <n-form-item-grid-item span="1 s:2" label="处理项目间的延迟 (秒)" path="delay_between_items_sec">
                        <n-input-number v-model:value="configModel.delay_between_items_sec" :min="0" :step="0.1" placeholder="例如: 0.5" style="width: 100%;" />
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item span="1 s:2" label="需手动处理的最低评分阈值" path="min_score_for_review">
                        <n-input-number v-model:value="configModel.min_score_for_review" :min="0.0" :max="10" :step="0.1" placeholder="例如: 6.0" style="width: 100%;" />
                        <template #feedback><n-text depth="3" style="font-size:0.8em;">评分低于此值的项目将进入待复核。</n-text></template>
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item span="1 s:2" label="最大演员数" path="max_actors_to_process">
                        <n-input-number v-model:value="configModel.max_actors_to_process" :min="10" :step="10" placeholder="建议 30-100" style="width: 100%;" />
                        <template #feedback><n-text depth="3" style="font-size:0.8em;">最终演员表数量，超过截断，优先保留有头像。</n-text></template>
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item label="角色名加前缀" path="actor_role_add_prefix">
                        <n-switch v-model:value="configModel.actor_role_add_prefix" />
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item label="移除无头像演员" path="remove_actors_without_avatars">
                        <n-switch v-model:value="configModel.remove_actors_without_avatars" />
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item label="关键词写入标签" path="keyword_to_tags">
                        <n-switch v-model:value="configModel.keyword_to_tags" />
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item label="工作室中文化" path="studio_to_chinese">
                        <n-switch v-model:value="configModel.studio_to_chinese" />
                      </n-form-item-grid-item>
                    </n-grid>
                  </n-card>
                </n-gi>

                <!-- 第二列：实时监控 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">实时监控</span></template>
                    <n-grid cols="1 s:2" :x-gap="12" :y-gap="8" responsive="screen">
                      <n-form-item-grid-item label="启用文件监控" path="monitor_enabled">
                        <n-switch v-model:value="configModel.monitor_enabled">
                          <template #checked>开启</template>
                          <template #unchecked>关闭</template>
                        </n-switch>
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="图片语言偏好" path="tmdb_image_language_preference">
                        <n-radio-group v-model:value="configModel.tmdb_image_language_preference" name="image_lang_group">
                          <n-space :size="8">
                            <n-radio value="zh">中文</n-radio>
                            <n-radio value="original">原语言</n-radio>
                          </n-space>
                        </n-radio-group>
                      </n-form-item-grid-item>

                      <n-form-item-grid-item span="1 s:2" label="监控路径" path="monitor_paths">
                        <n-input-group>
                          <n-select v-model:value="configModel.monitor_paths" multiple filterable tag :show-arrow="false" placeholder="输入路径或点击右侧选择" :options="[]" style="flex: 1;" />
                          <n-button type="primary" ghost @click="openLocalFolderSelector('monitor_paths', true)"><template #icon><n-icon :component="FolderIcon" /></template></n-button>
                        </n-input-group>
                      </n-form-item-grid-item>

                      <n-form-item-grid-item span="1 s:2" label="排除路径" path="monitor_exclude_dirs">
                        <n-input-group>
                          <n-select v-model:value="configModel.monitor_exclude_dirs" multiple filterable tag :show-arrow="false" placeholder="输入路径或点击右侧选择" :options="[]" style="flex: 1;" />
                          <n-button type="primary" ghost @click="openLocalFolderSelector('monitor_exclude_dirs', true)"><template #icon><n-icon :component="FolderIcon" /></template></n-button>
                        </n-input-group>
                        <template #feedback><n-text depth="3" style="font-size:0.8em;">命中路径将跳过刮削，仅刷新。</n-text></template>
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item label="排除刷新延迟" path="monitor_exclude_refresh_delay">
                        <n-input-number v-model:value="configModel.monitor_exclude_refresh_delay" :min="0" :step="10" placeholder="0" style="width: 100%"><template #suffix>秒</template></n-input-number>
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="定时扫描回溯" path="monitor_scan_lookback_days">
                        <n-input-number v-model:value="configModel.monitor_scan_lookback_days" :min="0" :max="365" placeholder="1" style="width: 100%"><template #suffix>天</template></n-input-number>
                      </n-form-item-grid-item>

                      <n-form-item-grid-item span="1 s:2" label="监控扩展名" path="monitor_extensions">
                        <n-select v-model:value="configModel.monitor_extensions" multiple filterable tag placeholder="输入扩展名并回车" :options="[]" />
                      </n-form-item-grid-item>
                    </n-grid>
                  </n-card>
                </n-gi>
                
                <!-- 第三列：数据源与API -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">数据源与API</span></template>
                    <n-grid cols="1 s:2" :x-gap="12" :y-gap="8" responsive="screen">
                      <n-form-item-grid-item span="1 s:2" label="本地数据源路径" path="local_data_path">
                        <n-input-group>
                          <n-input v-model:value="configModel.local_data_path" placeholder="缓存目录路径" @click="openLocalFolderSelector('local_data_path', false)"><template #prefix><n-icon :component="FolderIcon" /></template></n-input>
                          <n-button type="primary" ghost @click="openLocalFolderSelector('local_data_path', false)">选择</n-button>
                        </n-input-group>
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item span="1 s:2" label="TMDB API Key" path="tmdb_api_key">
                        <n-input type="password" show-password-on="mousedown" v-model:value="configModel.tmdb_api_key" placeholder="输入 TMDB API Key" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item span="1 s:2" label="TMDB API Base URL" path="tmdb_api_base_url">
                        <n-input v-model:value="configModel.tmdb_api_base_url" placeholder="https://api.themoviedb.org/3" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="成人内容探索" path="tmdb_include_adult">
                        <n-switch v-model:value="configModel.tmdb_include_adult" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="启用在线豆瓣" path="douban_enable_online_api">
                        <n-switch v-model:value="configModel.douban_enable_online_api" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="豆瓣冷却(秒)" path="api_douban_default_cooldown_seconds">
                        <n-input-number v-model:value="configModel.api_douban_default_cooldown_seconds" :min="0.1" :step="0.1" placeholder="1.0" style="width: 100%;" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item span="1 s:2" label="豆瓣登录 Cookie" path="douban_cookie">
                        <n-input type="password" show-password-on="mousedown" v-model:value="configModel.douban_cookie" placeholder="浏览器开发者工具中获取"/>
                      </n-form-item-grid-item>
                    </n-grid>
                  </n-card>
                </n-gi>
              </n-grid>
            </n-tab-pane>

            <!-- ================== 标签页 2: Emby ================== -->
            <n-tab-pane name="emby" tab="Emby & 302反代">
              <n-grid cols="1 l:2" :x-gap="16" :y-gap="16" responsive="screen">

                <!-- 左侧卡片: Emby 连接设置 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">Emby 连接设置</span></template>
                    <n-grid cols="1 m:2" :x-gap="12" :y-gap="8" responsive="screen">
                      <n-form-item-grid-item span="1 m:2">
                        <template #label>
                          <div style="display: flex; align-items: center; gap: 4px;">
                            <span>Emby URL</span>
                            <n-tooltip trigger="hover">
                              <template #trigger><n-icon :component="AlertIcon" class="info-icon" /></template>需要重启容器
                            </n-tooltip>
                          </div>
                        </template>
                        <n-input v-model:value="configModel.emby_server_url" placeholder="http://localhost:8096" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="外网URL" path="emby_public_url">
                        <n-input v-model:value="configModel.emby_public_url" placeholder="留空不开启" />
                      </n-form-item-grid-item>
                      <n-form-item-grid-item label="APIKey" path="emby_api_key">
                        <n-input v-model:value="configModel.emby_api_key" type="password" show-password-on="click" placeholder="API Key" />
                      </n-form-item-grid-item>

                      <n-form-item-grid-item label="用户ID" :rule="embyUserIdRule" path="emby_user_id">
                        <n-input v-model:value="configModel.emby_user_id" placeholder="32位" />
                        <template #feedback><div v-if="isInvalidUserId" style="color: #e88080; font-size: 12px;">格式错误！</div></template>
                      </n-form-item-grid-item>
                      <n-form-item-grid-item label="超时时间 (秒)" path="emby_api_timeout">
                        <n-input-number v-model:value="configModel.emby_api_timeout" :min="15" :step="5" placeholder="建议 30-90" style="width: 100%;" />
                      </n-form-item-grid-item>

                      <n-gi span="1 m:2"><n-divider title-placement="left" style="margin: 4px 0; font-size: 0.8em; color: gray;">管理员凭证 (选填)</n-divider></n-gi>
                      <n-form-item-grid-item label="用户名" path="emby_admin_user"><n-input v-model:value="configModel.emby_admin_user" placeholder="管理员用户名" /></n-form-item-grid-item>
                      <n-form-item-grid-item label="密码" path="emby_admin_pass"><n-input v-model:value="configModel.emby_admin_pass" type="password" show-password-on="click" placeholder="管理员密码" /></n-form-item-grid-item>

                      <n-gi span="1 m:2"><n-divider title-placement="left" style="margin: 4px 0;">选择处理的媒体库</n-divider></n-gi>
                      <n-form-item-grid-item label-placement="top" span="1 m:2">
                        <n-spin :show="loadingLibraries">
                          <n-checkbox-group v-model:value="configModel.libraries_to_process">
                            <n-space item-style="display: flex; flex-wrap: wrap;">
                              <n-checkbox v-for="lib in availableLibraries" :key="lib.Id" :value="lib.Id" :label="lib.Name" />
                            </n-space>
                          </n-checkbox-group>
                          <n-text depth="3" v-if="!loadingLibraries && availableLibraries.length === 0 && (configModel.emby_server_url && configModel.emby_api_key)">未找到库。请检查 URL 和 API Key。</n-text>
                          <div v-if="libraryError" style="color: red; margin-top: 5px;">{{ libraryError }}</div>
                        </n-spin>
                      </n-form-item-grid-item>
                    </n-grid>
                  </n-card>
                </n-gi>

                <!-- 右侧卡片: 虚拟库 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">302反代</span></template>
                    <n-grid cols="1 m:2" :x-gap="12" :y-gap="8" responsive="screen">
                      <n-form-item-grid-item label="启用反代" path="proxy_enabled">
                        <n-switch v-model:value="configModel.proxy_enabled" />
                      </n-form-item-grid-item>
                      <n-form-item-grid-item>
                        <template #label>
                          <div style="display: flex; align-items: center; gap: 4px;">
                            <span>端口</span>
                            <n-tooltip trigger="hover"><template #trigger><n-icon :component="AlertIcon" class="info-icon" /></template>需重启容器</n-tooltip>
                          </div>
                        </template>
                        <n-input-number v-model:value="configModel.proxy_port" :min="1025" :max="65535" :disabled="!configModel.proxy_enabled" style="width: 100%;" placeholder="8096"/>
                      </n-form-item-grid-item>
                      
                      <n-form-item-grid-item label="显示缺失海报" path="proxy_show_missing_placeholders">
                         <n-switch v-model:value="configModel.proxy_show_missing_placeholders" :disabled="!configModel.proxy_enabled"/>
                      </n-form-item-grid-item>
                      <n-form-item-grid-item label="合并原生库" path="proxy_merge_native_libraries">
                        <n-switch v-model:value="configModel.proxy_merge_native_libraries" :disabled="!configModel.proxy_enabled"/>
                      </n-form-item-grid-item>

                      <n-form-item-grid-item span="1 m:2" label="合并显示位置" path="proxy_native_view_order">
                        <n-radio-group v-model:value="configModel.proxy_native_view_order" :disabled="!configModel.proxy_enabled || !configModel.proxy_merge_native_libraries">
                          <n-radio value="before">原生在前</n-radio>
                          <n-radio value="after">原生在后</n-radio>
                        </n-radio-group>
                      </n-form-item-grid-item>

                      <n-gi span="1 m:2"><n-divider title-placement="left" style="margin: 4px 0;">选择合并原生库</n-divider></n-gi>
                      <n-form-item-grid-item span="1 m:2" v-if="configModel.proxy_enabled && configModel.proxy_merge_native_libraries" path="proxy_native_view_selection">
                        <n-spin :show="loadingNativeLibraries">
                          <n-checkbox-group v-model:value="configModel.proxy_native_view_selection">
                            <n-space item-style="display: flex; flex-wrap: wrap;">
                              <n-checkbox v-for="lib in nativeAvailableLibraries" :key="lib.Id" :value="lib.Id" :label="lib.Name"/>
                            </n-space>
                          </n-checkbox-group>
                        </n-spin>
                      </n-form-item-grid-item>
                    </n-grid>
                  </n-card>
                </n-gi>
              </n-grid>
            </n-tab-pane>

            <!-- ================== 标签页 3: 智能服务  ================== -->
            <n-tab-pane name="services" tab="智能服务">
              <n-grid cols="1 l:2" :x-gap="16" :y-gap="16" responsive="screen">
                
                <!-- 左侧: AI增强 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header>
                      <span class="card-title" style="white-space: nowrap; flex-shrink: 0; margin-right: 8px;">AI 增强</span>
                    </template>
                    <template #header-extra>
                      <n-space align="center" justify="end" :size="8">
                        <n-button size="tiny" type="info" ghost @click="openPromptModal">配置提示词</n-button>
                        <n-button size="tiny" type="primary" ghost @click="testAI" :loading="isTestingAI" :disabled="!configModel.ai_api_key">测试</n-button>
                      </n-space>
                    </template>
                    
                    <div class="ai-settings-wrapper">
                      <n-grid cols="1 m:2" :x-gap="12" :y-gap="8" responsive="screen">
                        <n-form-item-grid-item span="1 m:2" label="AI 服务商" path="ai_provider">
                          <n-select v-model:value="configModel.ai_provider" :options="aiProviderOptions" />
                        </n-form-item-grid-item>
                        <n-form-item-grid-item span="1 m:2" label="模型名称" path="ai_model_name">
                          <n-input v-model:value="configModel.ai_model_name" placeholder="gpt-3.5-turbo等" />
                        </n-form-item-grid-item>
                        <n-form-item-grid-item span="1 m:2" label="API Key" path="ai_api_key">
                          <n-input type="password" show-password-on="mousedown" v-model:value="configModel.ai_api_key" placeholder="输入 API Key" />
                        </n-form-item-grid-item>
                        <n-form-item-grid-item span="1 m:2" label="API Base URL (可选)" path="ai_base_url">
                          <n-input v-model:value="configModel.ai_base_url" placeholder="用于代理或兼容服务" />
                        </n-form-item-grid-item>

                        <n-gi span="1 m:2"><n-divider style="margin: 4px 0; font-size: 0.9em; color: gray;">功能与模式</n-divider></n-gi>

                        <n-form-item-grid-item span="1 m:2" label="启用功能">
                          <n-grid cols="2 sm:3" :y-gap="8" :x-gap="8" style="width: 100%">
                            <n-gi><n-checkbox v-model:checked="configModel.ai_translate_actor_role">演员角色翻译</n-checkbox></n-gi>
                            <n-gi><n-checkbox v-model:checked="configModel.ai_translate_title">片名翻译</n-checkbox></n-gi>
                            <n-gi><n-checkbox v-model:checked="configModel.ai_translate_overview">简介翻译</n-checkbox></n-gi>
                            <n-gi><n-checkbox v-model:checked="configModel.ai_translate_episode_overview">分集简介</n-checkbox></n-gi>
                            <n-gi><n-checkbox v-model:checked="configModel.ai_vector">生成媒体向量</n-checkbox></n-gi>
                            <n-gi><n-checkbox v-model:checked="configModel.ai_recognition">辅助识别</n-checkbox></n-gi>
                          </n-grid>
                        </n-form-item-grid-item>

                        <n-form-item-grid-item span="1 m:2" label="翻译模式" path="ai_translation_mode" v-if="configModel.ai_translate_actor_role || configModel.ai_translate_title_overview">
                          <n-radio-group v-model:value="configModel.ai_translation_mode" name="ai_translation_mode">
                            <n-space :size="16">
                              <n-radio value="fast">快速模式 (仅翻译)</n-radio>
                              <n-radio value="quality">顾问模式 (带上下文)</n-radio>
                            </n-space>
                          </n-radio-group>
                        </n-form-item-grid-item>
                      </n-grid>
                    </div>
                  </n-card>
                </n-gi>

                <!-- 右侧: MoviePilot & Telegram -->
                <n-gi>
                  <n-space vertical :size="16" style="height: 100%;">
                    
                    <!-- 卡片 A: MoviePilot 订阅 -->
                    <n-card :bordered="false" class="dashboard-card">
                      <template #header><span class="card-title">MoviePilot 订阅</span></template>
                      <!-- ★ 优化：合并排版，去掉多余分割线，全部紧凑双列显示 -->
                      <n-grid cols="1 m:2" :x-gap="12" :y-gap="8" responsive="screen">
                        <n-form-item-grid-item span="1 m:2" label="MoviePilot URL" path="moviepilot_url">
                          <n-input v-model:value="configModel.moviepilot_url" placeholder="http://192.168.1.100:3000"/>
                        </n-form-item-grid-item>
                        <n-form-item-grid-item label="用户名" path="moviepilot_username">
                          <n-input v-model:value="configModel.moviepilot_username" placeholder="登录用户名"/>
                        </n-form-item-grid-item>
                        <n-form-item-grid-item label="密码" path="moviepilot_password">
                          <n-input type="password" show-password-on="mousedown" v-model:value="configModel.moviepilot_password" placeholder="登录密码"/>
                        </n-form-item-grid-item>

                        <n-form-item-grid-item label="每日上限 (订阅规则)" path="resubscribe_daily_cap">
                          <n-input-number v-model:value="configModel.resubscribe_daily_cap" :min="1" :disabled="!isMoviePilotConfigured" style="width: 100%;" />
                        </n-form-item-grid-item>
                        <n-form-item-grid-item label="请求间隔(秒)" path="resubscribe_delay_seconds">
                          <n-input-number v-model:value="configModel.resubscribe_delay_seconds" :min="0.1" :step="0.1" :disabled="!isMoviePilotConfigured" style="width: 100%;" />
                        </n-form-item-grid-item>
                      </n-grid>
                    </n-card>

                    <!-- 卡片 B: Telegram 设置 -->
                    <n-card :bordered="false" class="dashboard-card">
                      <template #header><span class="card-title">Telegram 设置</span></template>
                      <template #header-extra>
                        <n-button size="tiny" type="primary" ghost @click="testTelegram" :loading="isTestingTelegram" :disabled="!configModel.telegram_bot_token || !configModel.telegram_channel_id">测试</n-button>
                      </template>
                      <!-- ★ 优化：内部双列，ID和通知事件在同一行 -->
                      <n-grid cols="1 s:2" :x-gap="12" :y-gap="8" responsive="screen">
                        <n-form-item-grid-item span="1 s:2" label="Bot Token" path="telegram_bot_token">
                          <n-input v-model:value="configModel.telegram_bot_token" type="password" show-password-on="click" placeholder="@BotFather 获取" />
                        </n-form-item-grid-item>
                        <n-form-item-grid-item label="频道/群组 ID" path="telegram_channel_id">
                          <n-input v-model:value="configModel.telegram_channel_id" placeholder="-100123456789" />
                        </n-form-item-grid-item>
                        <n-form-item-grid-item label="通知事件" path="telegram_notify_types">
                          <n-checkbox-group v-model:value="configModel.telegram_notify_types">
                            <n-space :size="16">
                              <n-checkbox value="library_new" label="入库" />
                              <n-checkbox value="playback" label="播放" />
                            </n-space>
                          </n-checkbox-group>
                        </n-form-item-grid-item>
                      </n-grid>
                    </n-card>

                  </n-space>
                </n-gi>
              </n-grid>
            </n-tab-pane>

            <!-- ================== 标签页 4: 高级 ================== -->
            <n-tab-pane name="advanced" tab="高级">
              <n-grid cols="1 m:2" :x-gap="16" :y-gap="16" responsive="screen">
                
                <!-- 左侧: 网络代理与日志配置 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">网络与系统日志</span></template>
                    <n-grid cols="1 s:2" :x-gap="12" :y-gap="8" responsive="screen">
                      
                      <!-- 网络代理 -->
                      <n-gi span="1 s:2"><n-divider title-placement="left" style="margin: 0; font-size: 0.9em; color: gray;">网络代理</n-divider></n-gi>
                      <n-form-item-grid-item span="1 s:2" label="启用网络代理" path="network_proxy_enabled">
                        <n-switch v-model:value="configModel.network_proxy_enabled" />
                        <template #feedback><n-text depth="3" style="font-size:0.8em;">为外部API请求启用 HTTP/HTTPS 代理。</n-text></template>
                      </n-form-item-grid-item>
                      <n-form-item-grid-item span="1 s:2" label="HTTP 代理地址" path="network_http_proxy_url">
                        <n-input-group>
                          <n-input v-model:value="configModel.network_http_proxy_url" placeholder="http://127.0.0.1:7890" :disabled="!configModel.network_proxy_enabled"/>
                          <n-button type="primary" ghost @click="testProxy" :loading="isTestingProxy" :disabled="!configModel.network_proxy_enabled || !configModel.network_http_proxy_url">测试</n-button>
                        </n-input-group>
                      </n-form-item-grid-item>

                      <!-- 日志配置 -->
                      <n-gi span="1 s:2"><n-divider title-placement="left" style="margin: 8px 0 0 0; font-size: 0.9em; color: gray;">日志配置</n-divider></n-gi>
                      <n-form-item-grid-item>
                        <template #label>
                          <n-space align="center" :size="4" :wrap="false">
                            <span>单文件大小 (MB)</span>
                            <n-tooltip trigger="hover"><template #trigger><n-icon :component="AlertIcon" class="info-icon" /></template>需重启生效</n-tooltip>
                          </n-space>
                        </template>
                        <n-input-number v-model:value="configModel.log_rotation_size_mb" :min="1" :step="1" placeholder="5" style="width: 100%;" />
                      </n-form-item-grid-item>
                      <n-form-item-grid-item>
                        <template #label>
                          <n-space align="center" :size="4" :wrap="false">
                            <span>日志备份数量</span>
                            <n-tooltip trigger="hover"><template #trigger><n-icon :component="AlertIcon" class="info-icon" /></template>需重启生效</n-tooltip>
                          </n-space>
                        </template>
                        <n-input-number v-model:value="configModel.log_rotation_backup_count" :min="1" :step="1" placeholder="10" style="width: 100%;" />
                      </n-form-item-grid-item>

                    </n-grid>
                  </n-card>
                </n-gi>

                <!-- 右侧: 数据管理 -->
                <n-gi>
                  <n-card :bordered="false" class="dashboard-card" style="height: 100%;">
                    <template #header><span class="card-title">数据管理</span></template>
                    <n-space vertical :size="8">
                      <n-space wrap :size="8">
                        <n-button @click="showExportModal" :loading="isExporting" size="small"><template #icon><n-icon :component="ExportIcon" /></template>导出</n-button>
                        <n-upload :custom-request="handleCustomImportRequest" :show-file-list="false" accept=".json.gz"><n-button :loading="isImporting" size="small"><template #icon><n-icon :component="ImportIcon" /></template>导入</n-button></n-upload>
                        <n-button @click="showClearTablesModal" :loading="isClearing" type="error" ghost size="small"><template #icon><n-icon :component="ClearIcon" /></template>清空表</n-button>
                        <n-popconfirm @positive-click="handleCleanupOfflineMedia">
                          <template #trigger>
                            <n-button type="warning" ghost :loading="isCleaningOffline" size="small"><template #icon><n-icon :component="OfflineIcon" /></template>清理离线</n-button>
                          </template>
                          确定清理不在库的离线元数据缓存吗？
                        </n-popconfirm>
                        <n-popconfirm @positive-click="handleClearVectors">
                          <template #trigger>
                            <n-button type="warning" ghost :loading="isClearingVectors" size="small"><template #icon><n-icon :component="FlashIcon" /></template>清空向量</n-button>
                          </template>
                          更换Embedding模型必须执行此操作，确定吗？
                        </n-popconfirm>
                        <n-popconfirm @positive-click="handleCorrectSequences">
                          <template #trigger>
                            <n-button type="warning" ghost :loading="isCorrecting" size="small"><template #icon><n-icon :component="BuildIcon" /></template>校准自增</n-button>
                          </template>
                          校准所有表的ID自增计数器？
                        </n-popconfirm>
                        <n-button type="warning" ghost :loading="isResettingMappings" size="small" @click="showResetMappingsModal"><template #icon><n-icon :component="SyncIcon" /></template>重置Emby</n-button>
                      </n-space>
                      <p class="description-text"><b>导出：</b>将数据库中的一个或多个表备份为 JSON.GZ 文件。<br><b>导入：</b>从 JSON.GZ 备份文件中恢复数据。<br><b>清空：</b>删除指定表中的所有数据，此操作不可逆。<br><b>清空向量：</b>更换ai后，必须执行此操作。不同模型生成的向量不兼容，混用会导致推荐结果完全错误。清空后需重新扫描生成。<br><b>清理离线：</b>移除已删除且无订阅状态的残留记录，给数据库瘦身。<br><b>校准：</b>修复导入数据可能引起的自增序号错乱的问题。<br><b>重置：</b>在重建 Emby 媒体库后，使用此功能清空所有旧的 Emby 关联数据（用户、合集、播放状态等），并保留核心元数据，以便后续重新扫描和关联。</p>
                    </n-space>
                  </n-card>
                </n-gi>

              </n-grid>
            </n-tab-pane>
          </n-tabs>

          <!-- 页面底部的统一保存按钮 -->
          <n-button type="primary" attr-type="submit" :loading="savingConfig" block size="large" style="margin-top: 24px;">
            保存所有设置
          </n-button>
        </n-form>
      </div>
      
      <n-alert v-else-if="configError" title="加载配置失败" type="error">
        {{ configError }}
      </n-alert>

      <div v-else>
        正在加载配置...
      </div>

    </n-space>

    <!-- ★★★ 本地物理目录选择器弹窗 ★★★ -->
    <n-modal v-model:show="showLocalFolderModal" preset="card" title="选择本地路径" style="width: 600px; max-width: 95vw;">
      <n-spin :show="loadingLocalFolders">
        <n-space vertical>
          <n-input-group>
            <n-input v-model:value="currentLocalPath" placeholder="当前路径" @keyup.enter="fetchLocalFolders(currentLocalPath)" />
            <n-button type="primary" @click="fetchLocalFolders(currentLocalPath)">
              <template #icon><n-icon :component="RefreshIcon" /></template>
            </n-button>
          </n-input-group>
          
          <n-list hoverable clickable bordered style="max-height: 400px; overflow-y: auto; border-radius: 6px;">
            <n-list-item v-for="folder in localFolders" :key="folder.path" @click="selectLocalFolder(folder)">
              <template #prefix>
                <n-icon :component="folder.is_parent ? ArrowUpIcon : FolderIcon" size="22" :color="folder.is_parent ? '#888' : '#f0a020'" />
              </template>
              <span :style="{ fontWeight: folder.is_parent ? 'bold' : 'normal' }">{{ folder.name }}</span>
            </n-list-item>
            <n-empty v-if="localFolders.length === 0" description="空目录或无权限访问" style="margin-top: 30px; margin-bottom: 30px;" />
          </n-list>
          
          <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px;">
            <n-button @click="showLocalFolderModal = false">取消</n-button>
            <n-button type="primary" @click="confirmLocalFolder">确定</n-button>
          </div>
        </n-space>
      </n-spin>
    </n-modal>
    
  </n-layout>
  
  <!-- 导出选项模态框 -->
  <n-modal v-model:show="exportModalVisible" preset="dialog" title="选择要导出的数据表" style="width: 600px; max-width: 95vw;">
    <n-space justify="end" style="margin-bottom: 10px;">
      <n-button text type="primary" @click="selectAllForExport">全选</n-button>
      <n-button text type="primary" @click="deselectAllForExport">全不选</n-button>
    </n-space>
    <n-checkbox-group v-model:value="tablesToExport" vertical>
      <n-grid :y-gap="8" :x-gap="16" cols="1 s:2" responsive="screen">
        <n-gi v-for="table in allDbTables" :key="table">
          <n-checkbox :value="table">
            {{ tableInfo[table]?.cn || table }}
            <span v-if="tableInfo[table]?.isSharable" class="sharable-label"> [可共享]</span>
          </n-checkbox>
        </n-gi>
      </n-grid>
    </n-checkbox-group>
    <template #action>
      <n-button @click="exportModalVisible = false">取消</n-button>
      <n-button type="primary" @click="handleExport" :disabled="tablesToExport.length === 0">确认导出</n-button>
    </template>
  </n-modal>
  
  <!-- 导入选项模态框 -->
  <n-modal v-model:show="importModalVisible" preset="dialog" title="恢复数据库备份" style="width: 600px; max-width: 95vw;">
    <n-space vertical>
      <div><p style="word-break: break-all;"><strong>文件名:</strong> {{ fileToImport?.name }}</p></div>
      
      <n-alert v-if="importMode === 'overwrite'" title="高危操作警告" type="warning">
        将使用备份数据 <strong class="warning-text">覆盖</strong> 数据库。此操作 <strong class="warning-text">不可逆</strong>！
      </n-alert>
      <n-alert v-else-if="importMode === 'share'" title="共享模式导入" type="info">
        检测到异机备份，将仅导入 <strong>可共享数据</strong>。
      </n-alert>
      
      <div>
        <n-text strong>选择要恢复的表</n-text>
        <n-space style="margin-left: 12px; display: inline-flex; vertical-align: middle;">
          <n-button size="tiny" text type="primary" @click="selectAllForImport">全选</n-button>
          <n-button size="tiny" text type="primary" @click="deselectAllForImport">全不选</n-button>
        </n-space>
      </div>
      <n-checkbox-group v-model:value="tablesToImport" @update:value="handleImportSelectionChange" vertical style="margin-top: 8px;">
        <n-grid :y-gap="8" :x-gap="16" cols="1 s:2" responsive="screen">
          <n-gi v-for="table in tablesInBackupFile" :key="table">
            <n-checkbox :value="table" :disabled="isTableDisabledForImport(table)">
              {{ tableInfo[table]?.cn || table }}
              <span v-if="tableInfo[table]?.isSharable" class="sharable-label"> [可共享]</span>
            </n-checkbox>
          </n-gi>
        </n-grid>
      </n-checkbox-group>
    </n-space>
    <template #action>
      <n-button @click="cancelImport">取消</n-button>
      <n-button type="primary" @click="confirmImport" :disabled="tablesToImport.length === 0">确认恢复</n-button>
    </template>
  </n-modal>

  <!-- 清空指定表模态框 -->
  <n-modal v-model:show="clearTablesModalVisible" preset="dialog" title="清空指定数据表" style="width: 600px; max-width: 95vw;">
    <n-space justify="end" style="margin-bottom: 10px;">
      <n-button text type="primary" @click="selectAllForClear">全选</n-button>
      <n-button text type="primary" @click="deselectAllForClear">全不选</n-button>
    </n-space>
    <n-alert title="高危警告" type="error" style="margin-bottom: 15px;">永久删除，不可恢复！</n-alert>
    <n-checkbox-group v-model:value="tablesToClear" @update:value="handleClearSelectionChange" vertical>
      <n-grid :y-gap="8" :x-gap="16" cols="1 s:2" responsive="screen">
        <n-gi v-for="table in allDbTables" :key="table">
          <n-checkbox :value="table">{{ tableInfo[table]?.cn || table }}</n-checkbox>
        </n-gi>
      </n-grid>
    </n-checkbox-group>
    <template #action>
      <n-button @click="clearTablesModalVisible = false">取消</n-button>
      <n-button type="error" @click="handleClearTables" :disabled="tablesToClear.length === 0" :loading="isClearing">确认清空</n-button>
    </template>
  </n-modal>

  <!-- 重置演员映射模态框 -->
  <n-modal v-model:show="resetMappingsModalVisible" preset="dialog" title="确认重置Emby数据">
    <n-alert title="高危警告" type="warning" style="margin-bottom: 15px;">
      <p style="margin: 0 0 8px 0;">清空所有Emby相关数据。保留元数据和映射，以便全量扫描后关联。</p>
      <p class="warning-text" style="margin: 0;"><strong>仅在重建 Emby 库时执行！</strong></p>
    </n-alert>
    <template #action>
      <n-button @click="resetMappingsModalVisible = false">取消</n-button>
      <n-button type="warning" @click="handleResetActorMappings" :loading="isResettingMappings">确认</n-button>
    </template>
  </n-modal>

  <!-- AI 提示词配置模态框 -->
  <n-modal v-model:show="promptModalVisible" preset="dialog" title="配置 AI 提示词" style="width: 800px; max-width: 95vw;">
    <n-alert type="info" style="margin-bottom: 16px;">
      自定义指令。<b>注意：</b>保留关键JSON输出格式要求。支持 <code>{title}</code> 占位符。
    </n-alert>
    <n-spin :show="loadingPrompts">
      <n-tabs type="segment" animated size="small">
        <n-tab-pane name="fast_mode" tab="快速"><n-input v-model:value="promptsModel.fast_mode" type="textarea" :autosize="{minRows:10, maxRows:20}" style="font-family: monospace;"/></n-tab-pane>
        <n-tab-pane name="quality_mode" tab="顾问"><n-input v-model:value="promptsModel.quality_mode" type="textarea" :autosize="{minRows:10, maxRows:20}" style="font-family: monospace;"/></n-tab-pane>
        <n-tab-pane name="overview_translation" tab="简介"><n-input v-model:value="promptsModel.overview_translation" type="textarea" :autosize="{minRows:10, maxRows:20}" style="font-family: monospace;"/><n-text depth="3" style="font-size: 12px;">变量: {title}, {overview}</n-text></n-tab-pane>
        <n-tab-pane name="title_translation" tab="标题"><n-input v-model:value="promptsModel.title_translation" type="textarea" :autosize="{minRows:10, maxRows:20}" style="font-family: monospace;"/><n-text depth="3" style="font-size: 12px;">变量: {media_type}, {title}, {year}</n-text></n-tab-pane>
        <n-tab-pane name="transliterate_mode" tab="音译"><n-input v-model:value="promptsModel.transliterate_mode" type="textarea" :autosize="{minRows:10, maxRows:20}" style="font-family: monospace;"/></n-tab-pane>
        <n-tab-pane name="filename_parsing" tab="识别"><n-input v-model:value="promptsModel.filename_parsing" type="textarea" :autosize="{minRows:10, maxRows:20}" style="font-family: monospace;"/></n-tab-pane>
      </n-tabs>
    </n-spin>
    <template #action>
      <n-space justify="space-between" style="width: 100%">
        <n-popconfirm @positive-click="resetPrompts"><template #trigger><n-button type="warning" ghost :loading="savingPrompts">重置</n-button></template>确定恢复默认？</n-popconfirm>
        <n-space><n-button @click="promptModalVisible = false">取消</n-button><n-button type="primary" @click="savePrompts" :loading="savingPrompts">保存</n-button></n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'; 
import { 
  NCard, NForm, NFormItem, NInputNumber, NSwitch, NButton, NGrid, NGi, 
  NSpin, NAlert, NInput, NSelect, NSpace, useMessage, useDialog,
  NFormItemGridItem, NCheckboxGroup, NCheckbox, NText, NRadioGroup, NRadio,
  NTag, NIcon, NUpload, NModal, NDivider, NInputGroup, NTabs, NTabPane, NTooltip
} from 'naive-ui';
import { 
  DownloadOutline as ExportIcon, 
  CloudUploadOutline as ImportIcon,
  TrashOutline as ClearIcon,
  BuildOutline as BuildIcon,
  AlertCircleOutline as AlertIcon,
  SyncOutline as SyncIcon,
  CloudOfflineOutline as OfflineIcon,
  FlashOutline as FlashIcon,
  Folder as FolderIcon,
  HomeOutline as HomeIcon, 
  ChevronForward as ChevronRightIcon, 
  Add as AddIcon,
  CheckmarkCircleOutline as CheckIcon,
  CloseCircleOutline as CloseIcon,
  ListOutline as ListIcon, 
  ColorWandOutline as ColorWandIcon,
  SearchOutline as SearchIcon,
  ArrowUpOutline as ArrowUpIcon,
  RefreshOutline as RefreshIcon
} from '@vicons/ionicons5';
import { useConfig } from '../../composables/useConfig.js';
import axios from 'axios';

const promptModalVisible = ref(false);
const loadingPrompts = ref(false);
const savingPrompts = ref(false);
const promptsModel = ref({
  fast_mode: '',
  quality_mode: '',
  overview_translation: '',
  title_translation: '',
  transliterate_mode: '',
  filename_parsing: ''
});

const tableInfo = {
  'app_settings': { cn: '基础配置', isSharable: false },
  'person_identity_map': { cn: '演员映射表', isSharable: true },
  'actor_metadata': { cn: '演员元数据', isSharable: true },
  'translation_cache': { cn: '翻译缓存', isSharable: true },
  'actor_subscriptions': { cn: '演员订阅配置', isSharable: false },
  'collections_info': { cn: '原生合集', isSharable: false },
  'processed_log': { cn: '已处理日志', isSharable: false },
  'failed_log': { cn: '待复核日志', isSharable: false },
  'custom_collections': { cn: '自建合集', isSharable: false },
  'media_metadata': { cn: '媒体元数据', isSharable: true },
  'resubscribe_rules': { cn: '媒体洗版规则', isSharable: false },
  'resubscribe_index': { cn: '媒体洗版缓存', isSharable: false },
  'cleanup_index': { cn: '媒体去重缓存', isSharable: false },
  'emby_users': { cn: 'Emby用户', isSharable: false },
  'user_media_data': { cn: 'Emby用户数据', isSharable: false },
  'user_templates': { cn: '用户权限模板', isSharable: false },
  'invitations': { cn: '邀请链接', isSharable: false },
  'emby_users_extended': { cn: 'Emby用户扩展信息', isSharable: false }
};
const tableDependencies = {
  'emby_users': ['user_media_data', 'emby_users_extended'],
  'user_templates': ['invitations']
};
const reverseTableDependencies = {};
for (const parent in tableDependencies) {
  for (const child of tableDependencies[parent]) {
    reverseTableDependencies[child] = parent;
  }
}
const handleClearSelectionChange = (currentSelection) => {
  const selectionSet = new Set(currentSelection);
  for (const parentTable in tableDependencies) {
    if (selectionSet.has(parentTable)) {
      const children = tableDependencies[parentTable];
      for (const childTable of children) {
        if (!selectionSet.has(childTable)) {
          selectionSet.add(childTable);
        }
      }
    }
  }
  if (selectionSet.size !== tablesToClear.value.length) {
    tablesToClear.value = Array.from(selectionSet);
  }
};
const handleImportSelectionChange = (currentSelection) => {
  const selectionSet = new Set(currentSelection);
  let changed = true;
  while (changed) {
    changed = false;
    const originalSize = selectionSet.size;
    for (const parentTable in tableDependencies) {
      if (selectionSet.has(parentTable)) {
        for (const childTable of tableDependencies[parentTable]) {
          selectionSet.add(childTable);
        }
      }
    }
    for (const childTable in reverseTableDependencies) {
      if (selectionSet.has(childTable)) {
        const parentTable = reverseTableDependencies[childTable];
        selectionSet.add(parentTable);
      }
    }
    if (selectionSet.size > originalSize) {
      changed = true;
    }
  }
  if (selectionSet.size !== tablesToImport.value.length) {
    tablesToImport.value = Array.from(selectionSet);
  }
};

const formRef = ref(null);
const formRules = { trigger: ['input', 'blur'] };
const { configModel, loadingConfig, savingConfig, configError, handleSaveConfig } = useConfig();
const message = useMessage();
const dialog = useDialog();
const isResettingMappings = ref(false);
const resetMappingsModalVisible = ref(false);
const availableLibraries = ref([]);
const loadingLibraries = ref(false);
const libraryError = ref(null);
const componentIsMounted = ref(false);
const nativeAvailableLibraries = ref([]);
const loadingNativeLibraries = ref(false);
const nativeLibraryError = ref(null);
let unwatchGlobal = null;
let unwatchEmbyConfig = null;
const isTestingProxy = ref(false);
const embyUserIdRegex = /^[a-f0-9]{32}$/i;
const isCleaningOffline = ref(false);
const isClearingVectors = ref(false);
const isTestingAI = ref(false);

const isInvalidUserId = computed(() => {
  if (!configModel.value || !configModel.value.emby_user_id) return false;
  return configModel.value.emby_user_id.trim() !== '' && !embyUserIdRegex.test(configModel.value.emby_user_id);
});
const embyUserIdRule = {
  trigger: ['input', 'blur'],
  validator(rule, value) {
    if (value && !embyUserIdRegex.test(value)) {
      return new Error('ID格式不正确，应为32位。');
    }
    return true;
  }
};
const showResetMappingsModal = () => { resetMappingsModalVisible.value = true; };
const handleResetActorMappings = async () => {
  isResettingMappings.value = true;
  try {
    const response = await axios.post('/api/actions/prepare-for-library-rebuild');
    message.success(response.data.message || 'Emby数据已成功重置！');
    resetMappingsModalVisible.value = false;
  } catch (error) {
    message.error(error.response?.data?.error || '重置失败，请检查后端日志。');
  } finally {
    isResettingMappings.value = false;
  }
};
const isMoviePilotConfigured = computed(() => {
  if (!configModel.value) return false;
  return !!(configModel.value.moviepilot_url && configModel.value.moviepilot_username && configModel.value.moviepilot_password);
});
const testProxy = async () => {
  if (!configModel.value.network_http_proxy_url) {
    message.warning('请先填写 HTTP 代理地址再进行测试。');
    return;
  }
  isTestingProxy.value = true;
  try {
    const response = await axios.post('/api/proxy/test', { url: configModel.value.network_http_proxy_url });
    if (response.data.success) {
      message.success(response.data.message);
    } else {
      message.error(`测试失败: ${response.data.message}`);
    }
  } catch (error) {
    const errorMsg = error.response?.data?.message || error.message;
    message.error(`测试请求失败: ${errorMsg}`);
  } finally {
    isTestingProxy.value = false;
  }
};
const testAI = async () => {
  if (!configModel.value.ai_api_key) {
    message.warning('请先填写 API Key 再进行测试。');
    return;
  }

  isTestingAI.value = true;
  try {
    const response = await axios.post('/api/ai/test', configModel.value);
    
    if (response.data.success) {
      dialog.success({
        title: 'AI 测试成功',
        content: response.data.message,
        positiveText: '太棒了'
      });
    } else {
      message.error(`测试失败: ${response.data.message}`);
    }
  } catch (error) {
    const errorMsg = error.response?.data?.message || error.message;
    dialog.error({
      title: 'AI 测试失败',
      content: errorMsg,
      positiveText: '好吧'
    });
  } finally {
    isTestingAI.value = false;
  }
};
const openPromptModal = async () => {
  promptModalVisible.value = true;
  loadingPrompts.value = true;
  try {
    const response = await axios.get('/api/ai/prompts');
    promptsModel.value = response.data;
  } catch (error) {
    message.error('加载提示词失败');
  } finally {
    loadingPrompts.value = false;
  }
};

const savePrompts = async () => {
  savingPrompts.value = true;
  try {
    await axios.post('/api/ai/prompts', promptsModel.value);
    message.success('提示词已保存');
    promptModalVisible.value = false;
  } catch (error) {
    message.error('保存失败');
  } finally {
    savingPrompts.value = false;
  }
};

const resetPrompts = async () => {
  savingPrompts.value = true;
  try {
    const response = await axios.post('/api/ai/prompts/reset');
    promptsModel.value = response.data.prompts;
    message.success('已恢复默认提示词');
  } catch (error) {
    message.error('重置失败');
  } finally {
    savingPrompts.value = false;
  }
};
const fetchNativeViewsSimple = async () => {
  if (!configModel.value?.emby_server_url || !configModel.value?.emby_api_key || !configModel.value?.emby_user_id) {
    nativeAvailableLibraries.value = [];
    return;
  }
  loadingNativeLibraries.value = true;
  nativeLibraryError.value = null;
  try {
    const userId = configModel.value.emby_user_id;
    const response = await axios.get(`/api/emby/user/${userId}/views`, { headers: { 'X-Emby-Token': configModel.value.emby_api_key } });
    const items = response.data?.Items || [];
    nativeAvailableLibraries.value = items.map(i => ({ Id: i.Id, Name: i.Name, CollectionType: i.CollectionType }));
    if (nativeAvailableLibraries.value.length === 0) nativeLibraryError.value = "未找到原生媒体库。";
  } catch (err) {
    nativeAvailableLibraries.value = [];
    nativeLibraryError.value = `获取原生媒体库失败: ${err.response?.data?.error || err.message}`;
  } finally {
    loadingNativeLibraries.value = false;
  }
};
watch(() => configModel.value?.refresh_emby_after_update, (isRefreshEnabled) => {
  if (configModel.value && !isRefreshEnabled) {
    configModel.value.auto_lock_cast_after_update = false;
  }
});
watch(() => [configModel.value?.proxy_enabled, configModel.value?.proxy_merge_native_libraries, configModel.value?.emby_server_url, configModel.value?.emby_api_key, configModel.value?.emby_user_id], ([proxyEnabled, mergeNative, url, apiKey, userId]) => {
  if (proxyEnabled && mergeNative && url && apiKey && userId) {
    fetchNativeViewsSimple();
  } else {
    nativeAvailableLibraries.value = [];
  }
}, { immediate: true });
const aiProviderOptions = ref([
  { label: 'OpenAI (及兼容服务)', value: 'openai' },
  { label: '智谱AI (ZhipuAI)', value: 'zhipuai' },
  { label: 'Google Gemini', value: 'gemini' },
]);
const isExporting = ref(false);
const exportModalVisible = ref(false);
const allDbTables = ref([]);
const tablesToExport = ref([]);
const isImporting = ref(false);
const importModalVisible = ref(false);
const fileToImport = ref(null);
const tablesInBackupFile = ref([]);
const tablesToImport = ref([]);
const clearTablesModalVisible = ref(false);
const tablesToClear = ref([]);
const isClearing = ref(false);
const isCorrecting = ref(false);
const importMode = ref('overwrite');
const isTableDisabledForImport = (table) => {
  return importMode.value === 'share' && !tableInfo[table]?.isSharable;
};
const showClearTablesModal = async () => {
  try {
    const response = await axios.get('/api/database/tables');
    allDbTables.value = response.data;
    tablesToClear.value = [];
    clearTablesModalVisible.value = true;
  } catch (error) {
    message.error('无法获取数据库表列表，请检查后端日志。');
  }
};
const handleClearTables = async () => {
  if (tablesToClear.value.length === 0) {
    message.warning('请至少选择一个要清空的数据表。');
    return;
  }
  isClearing.value = true;
  try {
    const response = await axios.post('/api/actions/clear_tables', { tables: tablesToClear.value });
    message.success(response.data.message || '成功清空所选数据表！');
    clearTablesModalVisible.value = false;
    tablesToClear.value = [];
  } catch (error) {
    const errorMsg = error.response?.data?.error || '清空操作失败，请检查后端日志。';
    message.error(errorMsg);
  } finally {
    isClearing.value = false;
  }
};
const selectAllForClear = () => tablesToClear.value = [...allDbTables.value];
const deselectAllForClear = () => tablesToClear.value = [];

// --- 本地目录浏览器状态 ---
const showLocalFolderModal = ref(false)
const currentLocalPath = ref('')
const localFolders = ref([])
const loadingLocalFolders = ref(false)
const currentLocalTargetField = ref('')
const isCurrentLocalTargetArray = ref(false)

// 打开本地目录浏览器
const openLocalFolderSelector = (targetField, isArray = false) => {
    currentLocalTargetField.value = targetField
    isCurrentLocalTargetArray.value = isArray
    
    // 决定初始路径
    let startPath = '/'
    if (!isArray && configModel.value[targetField]) {
        startPath = configModel.value[targetField]
    } else if (isArray && configModel.value[targetField] && configModel.value[targetField].length > 0) {
        // 如果是数组且有值，取最后一个值的父目录作为起点，方便连续添加
        const lastPath = configModel.value[targetField][configModel.value[targetField].length - 1]
        startPath = lastPath.substring(0, lastPath.lastIndexOf('/')) || '/'
    }
    
    currentLocalPath.value = startPath
    showLocalFolderModal.value = true
    fetchLocalFolders(currentLocalPath.value)
}

// 获取本地目录列表
const fetchLocalFolders = async (path) => {
    loadingLocalFolders.value = true
    try {
        const res = await axios.get('/api/system/directories', { params: { path } })
        if (res.data.code === 200) {
            localFolders.value = res.data.data
            if (res.data.current_path !== undefined) {
                currentLocalPath.value = res.data.current_path
            }
        } else {
            message.error(res.data.message || '获取目录失败')
        }
    } catch (error) {
        if (error.response && error.response.status === 403) {
            message.error('没有权限访问该目录！')
        } else if (error.response && error.response.status === 404) {
            message.error('目录不存在！')
        } else {
            message.error('请求目录失败: ' + (error.response?.data?.message || error.message))
        }
    } finally {
        loadingLocalFolders.value = false
    }
}

// 点击列表中的文件夹
const selectLocalFolder = (folder) => {
    fetchLocalFolders(folder.path)
}

// 确认选择
const confirmLocalFolder = () => {
    const field = currentLocalTargetField.value
    const path = currentLocalPath.value
    
    if (isCurrentLocalTargetArray.value) {
        if (!configModel.value[field]) {
            configModel.value[field] = []
        }
        if (!configModel.value[field].includes(path)) {
            configModel.value[field].push(path)
            message.success(`已追加路径: ${path}`)
        } else {
            message.warning('该路径已存在列表中')
        }
    } else {
        configModel.value[field] = path
        message.success(`已选择路径: ${path}`)
    }
    
    showLocalFolderModal.value = false
}


const save = async () => {
  try {
    await formRef.value?.validate();
    const cleanConfigPayload = JSON.parse(JSON.stringify(configModel.value));
    if (configModel.value) {
        cleanConfigPayload.libraries_to_process = configModel.value.libraries_to_process;
        cleanConfigPayload.proxy_native_view_selection = configModel.value.proxy_native_view_selection;
    }
    const success = await handleSaveConfig(cleanConfigPayload);
    if (success) {
      message.success('所有设置已成功保存！');
    } else {
      message.error(configError.value || '配置保存失败，请检查后端日志。');
    }
  } catch (errors) {
    message.error('请检查表单中的必填项或错误项！');
  }
};
const fetchEmbyLibrariesInternal = async () => {
  if (!configModel.value.emby_server_url || !configModel.value.emby_api_key) {
    availableLibraries.value = [];
    return;
  }
  if (loadingLibraries.value) return;
  loadingLibraries.value = true;
  libraryError.value = null;
  try {
    const response = await axios.get(`/api/emby_libraries`);
    availableLibraries.value = response.data || [];
    if (availableLibraries.value.length === 0) libraryError.value = "获取到的媒体库列表为空。";
  } catch (err) {
    availableLibraries.value = [];
    libraryError.value = `获取 Emby 媒体库失败: ${err.response?.data?.error || err.message}`;
  } finally {
    loadingLibraries.value = false;
  }
};
const showExportModal = async () => {
  try {
    const response = await axios.get('/api/database/tables');
    allDbTables.value = response.data;
    tablesToExport.value = [...response.data];
    exportModalVisible.value = true;
  } catch (error) {
    message.error('无法获取数据库表列表，请检查后端日志。');
  }
};
const handleExport = async () => {
  isExporting.value = true;
  exportModalVisible.value = false;
  try {
    const response = await axios.post('/api/database/export', { tables: tablesToExport.value }, { responseType: 'blob' });
    const contentDisposition = response.headers['content-disposition'];
    let filename = 'database_backup.json';
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?(.+?)"?$/);
      if (match?.[1]) filename = match[1];
    }
    const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = blobUrl;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(blobUrl);
    message.success('数据已开始导出下载！');
  } catch (err) {
    message.error('导出数据失败，请查看日志。');
  } finally {
    isExporting.value = false;
  }
};
const selectAllForExport = () => tablesToExport.value = [...allDbTables.value];
const deselectAllForExport = () => tablesToExport.value = [];

const handleCustomImportRequest = async ({ file }) => {
  const rawFile = file.file;
  if (!rawFile) {
    message.error("未能获取到文件对象。");
    return;
  }

  const msgReactive = message.loading('正在解析备份文件...', { duration: 0 });
  
  try {
    const formData = new FormData();
    formData.append('file', rawFile);
    const response = await axios.post('/api/database/preview-backup', formData);

    msgReactive.destroy();

    const tables = response.data.tables;
    if (!tables || tables.length === 0) {
      message.error('备份文件有效，但其中不包含任何数据表。');
      return;
    }

    fileToImport.value = rawFile;
    tablesInBackupFile.value = tables;
    importMode.value = response.data.import_mode || 'overwrite'; 

    if (importMode.value === 'share') {
      tablesToImport.value = tables.filter(t => tableInfo[t]?.isSharable);
      message.info("已进入共享导入模式，默认仅选择可共享的数据。");
    } else {
      tablesToImport.value = [...tables];
    }
    
    importModalVisible.value = true;

  } catch (error) {
    msgReactive.destroy();
    const errorMsg = error.response?.data?.error || '解析备份文件失败，请检查文件是否有效。';
    message.error(errorMsg);
  }
};

const isTestingTelegram = ref(false);

const testTelegram = async () => {
  if (!configModel.value.telegram_bot_token || !configModel.value.telegram_channel_id) {
    message.warning('请先填写 Bot Token 和 频道 ID。');
    return;
  }

  isTestingTelegram.value = true;
  try {
    const response = await axios.post('/api/telegram/test', {
      token: configModel.value.telegram_bot_token,
      chat_id: configModel.value.telegram_channel_id
    });
    
    if (response.data.success) {
      message.success(response.data.message);
    } else {
      message.error(`测试失败: ${response.data.message}`);
    }
  } catch (error) {
    const errorMsg = error.response?.data?.message || error.message;
    message.error(`请求失败: ${errorMsg}`);
  } finally {
    isTestingTelegram.value = false;
  }
};

const cancelImport = () => {
  importModalVisible.value = false;
  fileToImport.value = null;
};

const confirmImport = () => {
  importModalVisible.value = false; 
  startImportProcess();   
};

const startImportProcess = () => {
  if (!fileToImport.value) {
    message.error("没有要上传的文件。");
    return;
  }
  isImporting.value = true;
  const msgReactive = message.loading('正在上传并恢复数据...', { duration: 0 });

  const formData = new FormData();
  formData.append('file', fileToImport.value);
  formData.append('tables', tablesToImport.value.join(','));

  axios.post('/api/database/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  .then(response => {
    msgReactive.destroy();
    message.success(response.data?.message || '恢复任务已成功提交！');
  })
  .catch(error => {
    msgReactive.destroy();
    const errorMsg = error.response?.data?.error || '恢复失败，未知错误。';
    message.error(errorMsg, { duration: 8000 });
  })
  .finally(() => {
    isImporting.value = false;
    fileToImport.value = null;
  });
};

const handleCleanupOfflineMedia = async () => {
  isCleaningOffline.value = true;
  try {
    const response = await axios.post('/api/actions/cleanup-offline-media');
    const stats = response.data.data || {};
    const deletedCount = stats.media_metadata_deleted || 0;
    
    if (deletedCount > 0) {
      message.success(`瘦身成功！已清除 ${deletedCount} 条无效的离线记录。`);
    } else {
      message.success('数据库非常干净，没有发现需要清理的离线记录。');
    }
  } catch (error) {
    message.error(error.response?.data?.error || '清理失败，请检查后端日志。');
  } finally {
    isCleaningOffline.value = false;
  }
};

const handleClearVectors = async () => {
  isClearingVectors.value = true;
  try {
    const response = await axios.post('/api/actions/clear-vectors');
    message.success(response.data.message || '向量数据已清空！');
  } catch (error) {
    message.error(error.response?.data?.error || '操作失败，请检查后端日志。');
  } finally {
    isClearingVectors.value = false;
  }
};

const selectAllForImport = () => tablesToImport.value = [...tablesInBackupFile.value];
const deselectAllForImport = () => tablesToImport.value = [];

const handleCorrectSequences = async () => {
  isCorrecting.value = true;
  try {
    const response = await axios.post('/api/database/correct-sequences');
    message.success(response.data.message || 'ID计数器校准成功！');
  } catch (error) {
    message.error(error.response?.data?.error || '校准失败，请检查后端日志。');
  } finally {
    isCorrecting.value = false;
  }
};

onMounted(async () => {
  componentIsMounted.value = true;
  unwatchGlobal = watch(loadingConfig, (isLoading) => {
    if (!isLoading && componentIsMounted.value && configModel.value) {
      if (configModel.value.emby_server_url && configModel.value.emby_api_key) {
        fetchEmbyLibrariesInternal();
      }
      if (unwatchGlobal) { unwatchGlobal(); }
    }
  }, { immediate: true });
  unwatchEmbyConfig = watch(() => [configModel.value?.emby_server_url, configModel.value?.emby_api_key], (newValues, oldValues) => {
    if (componentIsMounted.value && oldValues) {
      if (newValues[0] !== oldValues[0] || newValues[1] !== oldValues[1]) {
        fetchEmbyLibrariesInternal();
      }
    }
  });
});
onUnmounted(() => {
  componentIsMounted.value = false;
  if (unwatchGlobal) unwatchGlobal();
  if (unwatchEmbyConfig) unwatchEmbyConfig();
});
</script>

<style scoped>
/* 极力减小底部边距，让排布更加紧凑 */
:deep(.n-form-item) {
  margin-bottom: 4px;
}

/* 标签底部留白去除，提升空间利用率 */
:deep(.n-form-item-label) {
  padding-bottom: 0px !important;
}

.ai-settings-wrapper {
  transition: opacity 0.3s ease;
}
.content-disabled {
  opacity: 0.6;
}

.engine-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.engine-tag {
  cursor: grab;
}
.engine-tag:active {
  cursor: grabbing;
}
.drag-handle {
  margin-right: 6px;
  vertical-align: -0.15em;
}

.description-text {
  font-size: 0.85em;
  color: var(--n-text-color-3);
  margin: 0;
  line-height: 1.6;
}
.warning-text {
  color: var(--n-warning-color-suppl); 
  font-weight: bold;
}
.sharable-label {
  color: var(--n-info-color-suppl);
  font-size: 0.9em;
  margin-left: 4px;
  font-weight: normal;
}
.glass-section {
  background-color: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}
.info-icon {
  color: var(--n-info-color);
  cursor: help;
  font-size: 16px;
  vertical-align: middle;
}
.rules-container { background: transparent; border: none; padding: 0; }
.rule-item {
  display: flex; align-items: center; background-color: var(--n-action-color); 
  border: 1px solid var(--n-divider-color); padding: 12px; margin-bottom: 8px; border-radius: 6px; transition: all 0.2s;
}
.rule-item:hover { border-color: var(--n-primary-color); background-color: var(--n-hover-color); }
.rule-info { flex: 1; }
.rule-name { font-weight: bold; font-size: 13px; color: var(--n-text-color-1); }
.rule-desc span { color: var(--n-text-color-3); }
.rule-actions { display: flex; align-items: center; gap: 4px; }
</style>