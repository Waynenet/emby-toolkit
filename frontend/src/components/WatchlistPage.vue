<!-- src/components/WatchlistPage.vue -->
<template>
  <div :content-style="{ padding: isMobile ? '12px' : '24px' }">
    <div class="watchlist-page">
      <n-page-header>
        <template #title>
          <n-space align="center">
            <span>智能追剧列表</span>
            <n-tag v-if="filteredWatchlist.length > 0" type="info" round :bordered="false" size="small">
              {{ filteredWatchlist.length }} 部
            </n-tag>
          </n-space>
        </template>
        <n-alert v-if="!isMobile" title="操作提示" type="info" style="margin-top: 24px;">
          <li>本模块高度自动化，几乎无需人工干涉。新入库剧集，会自动判断是否完结，未完结剧集会进入追剧列表，并根据状态自动处理。</li>
          <li>当剧集完结后，会转入已完结列表，后台可以设置定时刷新剧集元数据以及有新季上线会自动转成追剧中，并从上线之日开始自动订阅新季。</li>
          <li>不想继续追踪某一季时，可以强制完结该季；后续刷新不会把该季自动改回追剧中，也不会影响同剧其它季。</li>
        </n-alert>
        <template #extra>
          <n-space>
            <n-dropdown
              v-if="selectedItems.length > 0"
              trigger="click"
              :options="batchActions"
              @select="handleBatchAction"
            >
              <n-button size="small" type="primary">
                批量操作 ({{ selectedItems.length }})
                <template #icon><n-icon :component="CaretDownIcon" /></template>
              </n-button>
            </n-dropdown>
            <n-radio-group v-model:value="currentView" size="small">
              <n-radio-button value="inProgress">追剧中</n-radio-button>
              <n-radio-button value="completed">已完结</n-radio-button>
            </n-radio-group>
            <n-popconfirm @positive-click="addAllSeriesToWatchlist">
              <template #trigger>
                <n-button size="small" :loading="isAddingAll">
                  <template #icon><n-icon :component="ScanIcon" /></template>
                  一键扫描
                </n-button>
              </template>
              确定要扫描 Emby 选定的媒体库中的所有剧集吗？<br />
              此操作会忽略已在列表中的剧集，只添加新的。
            </n-popconfirm>

            <n-button size="small" @click="triggerBackfillTask" :loading="isBackfilling">
              <template #icon><n-icon :component="BackfillIcon" /></template>
              补全旧季
            </n-button>

            <n-button size="small" @click="triggerAllWatchlistUpdate" :loading="isBatchUpdating">
              <template #icon><n-icon :component="SyncOutline" /></template>
              刷新追剧
            </n-button>
            <n-button size="small" @click="openConfigModal">
              <template #icon><n-icon :component="SettingsIcon" /></template>
              策略配置
            </n-button>
          </n-space>
        </template>
      </n-page-header>
      <n-divider />

      <n-space :wrap="true" :size="[20, 12]" style="margin-bottom: 20px; align-items: center;">
        
        <n-checkbox 
          :checked="isAllSelected" 
          :indeterminate="isIndeterminate"
          @update:checked="handleSelectAll"
          style="margin-right: 8px;"
        >
          全选 ({{ filteredWatchlist.length }})
        </n-checkbox>

        <n-input v-model:value="searchQuery" placeholder="按名称搜索..." clearable style="min-width: 200px;" />
        
        <n-select
          v-if="currentView === 'inProgress'"
          v-model:value="filterStatus"
          :options="statusFilterOptions"
          style="min-width: 140px;"
        />
        
        <n-select
          v-model:value="filterMissing"
          :options="missingFilterOptions"
          style="min-width: 140px;"
        />
        
        <n-select
          v-if="currentView === 'completed'"
          v-model:value="filterGaps"
          :options="gapsFilterOptions"
          style="min-width: 140px;"
        />
        
        <n-select
          v-model:value="sortKey"
          :options="sortKeyOptions"
          style="min-width: 160px;"
        />
        
        <n-button-group>
          <n-button @click="sortOrder = 'asc'" :type="sortOrder === 'asc' ? 'primary' : 'default'" ghost>
            <template #icon><n-icon :component="ArrowUpIcon" /></template>
            升序
          </n-button>
          <n-button @click="sortOrder = 'desc'" :type="sortOrder === 'desc' ? 'primary' : 'default'" ghost>
            <template #icon><n-icon :component="ArrowDownIcon" /></template>
            降序
          </n-button>
        </n-button-group>
      </n-space>

      <div v-if="isLoading" class="center-container"><n-spin size="large" /></div>
      <div v-else-if="error" class="center-container"><n-alert title="加载错误" type="error" style="max-width: 500px;">{{ error }}</n-alert></div>
      <div v-else-if="filteredWatchlist.length > 0">
        
        <!-- Grid 容器 -->
        <div class="responsive-grid">
          <div 
            v-for="(item, i) in renderedWatchlist" 
            :key="item.tmdb_id" 
            class="grid-item"
          >
            <n-card class="dashboard-card series-card" :bordered="false" @click="toggleSelection(item.tmdb_id, $event, i)">
              
              <!-- ★★★ 核心结构：card-inner-layout 包裹层 ★★★ -->
              <div class="card-inner-layout">
                
                <!-- 左侧海报 -->
                <div class="card-poster-container">
                  <!-- 移动到这里，绝对定位漂浮在图片上 -->
                  <div class="poster-checkbox-wrap" @click.stop>
                    <!-- 修改点：加上 size="small" -->
                    <n-checkbox
                      size="small"
                      :checked="selectedItems.includes(item.tmdb_id)"
                      @update:checked="(checked, event) => toggleSelection(item.tmdb_id, event, i)"
                    />
                  </div>

                  <n-image lazy :src="getPosterUrl(item.emby_item_ids_json)" class="card-poster" object-fit="cover" @click.stop>
                    <template #placeholder><div class="poster-placeholder"><n-icon :component="TvIcon" size="32" /></div></template>
                  </n-image>
                  
                  <!-- 海报上的集数浮层 -->
                  <div class="poster-overlay">
                    <div class="overlay-content" @click.stop>
                      <n-popover 
                        trigger="click" 
                        placement="top" 
                        style="padding: 10px;"
                        v-model:show="item.show_edit_popover"
                        @update:show="(show) => { if(show) tempTotalEpisodes = item.total_count || item.collected_count }"
                      >
                        <template #trigger>
                          <span class="episode-count clickable-count" title="点击修正总集数">
                            {{ item.collected_count || 0 }} / {{ item.total_count || 0 }}
                          </span>
                        </template>
                        
                        <div style="display: flex; flex-direction: column; gap: 12px; width: 220px;">
  
                          <!-- 1. 原有的总集数修正 -->
                          <div style="display: flex; flex-direction: column; gap: 4px;">
                            <n-text strong depth="1">修正总集数 (单季有效)</n-text>
                            <n-input-number 
                              v-model:value="tempTotalEpisodes" 
                              size="small" 
                              :min="item.collected_count || 0"
                              placeholder="输入实际集数"
                            />
                            <n-space justify="end" size="small" style="margin-top: 4px;">
                              <n-button size="tiny" @click="tempTotalEpisodes = item.collected_count">填入当前</n-button>
                              <n-button type="primary" size="tiny" @click="saveTotalEpisodes(item)">保存集数</n-button>
                            </n-space>
                          </div>
                        
                          <n-divider style="margin: 0" />
                        
                          <!-- 2. ★★★ 新增：TMDb 剧集组绑定 ★★★ -->
                          <div style="display: flex; flex-direction: column; gap: 4px;">
                            <n-text strong depth="1">TMDb 剧集组 (全剧洗牌)</n-text>
                            <n-text depth="3" style="font-size: 12px;">长篇动漫解决分季混乱的神器！</n-text>

                            <n-select
                              v-model:value="item.temp_group_id"
                              :options="item.available_groups || []"
                              :loading="item.loading_groups"
                              placeholder="加载中..."
                              size="small"
                              clearable
                              @click="fetchEpisodeGroups(item)"
                            />

                            <n-button 
                              type="warning" 
                              size="tiny" 
                              block 
                              style="margin-top: 4px;"
                              :disabled="item.temp_group_id === item.saved_group_id"
                              @click="saveEpisodeGroup(item)"
                            >
                              保存并重铸全剧
                            </n-button>
                          </div>

                        </div>
                      </n-popover>
                    </div>
                  </div>
                </div>

                <!-- 右侧内容 -->
                <div class="card-content-container">
                  <div class="card-header">
                    <!-- 🚀 修改：将文本嵌套在 a 标签中，实现点击片名跳转 TMDb 并阻止冒泡 -->
                    <n-ellipsis class="card-title click-title" :tooltip="{ style: { maxWidth: '300px' } }">
                      <a 
                        :href="`https://www.themoviedb.org/tv/${item.parent_tmdb_id}`" 
                        target="_blank" 
                        @click.stop
                        style="text-decoration: none; color: inherit;"
                      >
                        {{ item.item_name }}
                      </a>
                    </n-ellipsis>
                    
                    <n-popconfirm @positive-click="() => removeFromWatchlist(item.parent_tmdb_id, item.item_name)" @click.stop>
                      <template #trigger>
                        <n-button text type="error" size="small" @click.stop>
                          <template #icon><n-icon :component="TrashIcon" /></template>
                        </n-button>
                      </template>
                      确定要从追剧列表中移除《{{ item.item_name }}》吗？
                    </n-popconfirm>
                  </div>
                  <div class="card-status-area">
                    <n-space vertical size="small">
                      <!-- 1. 顶部状态按钮 (保持不变) -->
                      <n-space align="center" :wrap="false">
                        <!-- 已完结视图 (聚合卡片) -->
                        <template v-if="currentView === 'completed'">
                          <n-tag round size="small" :bordered="false" :type="getSeriesStatusUI(item).type">
                            <template #icon><n-icon :component="getSeriesStatusUI(item).icon" /></template>
                            {{ getSeriesStatusUI(item).text }}
                          </n-tag>
                        </template>
                        <!-- 追剧中视图 (分季卡片) -->
                        <template v-else>
                          <n-button round size="tiny" :type="statusInfo(item.status).type" @click.stop="() => updateStatus(item.tmdb_id, statusInfo(item.status).next)" :title="`点击切换到 '${statusInfo(item.status).nextText}'`">
                            <template #icon><n-icon :component="statusInfo(item.status).icon" /></template>
                            {{ statusInfo(item.status).text }}
                          </n-button>
                        </template>
                      </n-space>

                      <!-- ★★★ 2. 聚合信息展示区 (仅聚合卡片显示) ★★★ -->
                      <template v-if="item.is_aggregated">
                        <!-- A. 包含 (已入库) -->
                        <div v-if="item.seasons_contains && item.seasons_contains.length > 0" class="info-line">
                          <n-icon :component="CollectionsIcon" class="icon-fix" />
                          <span class="info-line-text">
                            包含: {{ item.seasons_contains.length }} 个季度 ({{ formatSeasonRange(item.seasons_contains) }})
                          </span>
                        </div>

                        <div v-if="item.seasons_force_ended && item.seasons_force_ended.length > 0" class="info-line">
                          <n-icon :component="ForceEndIcon" class="icon-fix" style="color: var(--n-warning-color)" />
                          <n-text :depth="3" style="color: var(--n-warning-color)">
                            强制完结: {{ item.seasons_force_ended.length }} 个季度 ({{ formatSeasonRange(item.seasons_force_ended) }})
                          </n-text>
                        </div>

                        <!-- B. 连载 (在库且活跃) - 绿色高亮 -->
                        <div v-if="item.seasons_airing && item.seasons_airing.length > 0" class="info-line success-text">
                          <n-icon :component="WatchingIcon" class="icon-fix" />
                          <span class="info-line-text">
                            连载: {{ item.seasons_airing.length }} 个季度 ({{ formatSeasonRange(item.seasons_airing) }})
                          </span>
                        </div>

                        <!-- C. 缺失 (未入库) - 红色高亮 -->
                        <div v-if="item.seasons_missing && item.seasons_missing.length > 0" class="info-line error-text">
                          <n-icon :component="DownloadIcon" class="icon-fix" />
                          <span class="info-line-text">
                            缺失: {{ item.seasons_missing.length }} 个季度 ({{ formatSeasonRange(item.seasons_missing) }})
                          </span>
                        </div>
                      </template>

                      <!-- ★★★ 3. 单季详细信息 (仅非聚合卡片显示) ★★★ -->
                      <template v-else>
                        <!-- 待播集数 -->
                        <div v-if="nextEpisode(item)?.name" class="info-line">
                          <n-icon :component="TvIcon" class="icon-fix" />
                          <span class="info-line-text" style="flex: 1; min-width: 0;">
                            <n-ellipsis>待播集: {{ nextEpisode(item).name }}</n-ellipsis>
                          </span>
                        </div>

                        <!-- 播出时间 -->
                        <div v-if="nextEpisode(item)?.name" class="info-line">
                          <n-icon :component="CalendarIcon" class="icon-fix" />
                          <span class="info-line-text">
                            播出时间: {{ nextEpisode(item).air_date ? formatAirDate(nextEpisode(item).air_date) : '待定' }}
                          </span>
                        </div>

                        <!-- 上次检查 -->
                        <div class="info-line">
                          <n-icon :component="TimeIcon" class="icon-fix" />
                          <span class="info-line-text">上次检查: {{ formatTimestamp(item.last_checked_at) }}</span>
                        </div>
                      </template>
                    </n-space>
                  </div>
                  
                  <!-- 进度条作为分隔线 -->
                  <div class="progress-separator">
                    <n-progress 
                      type="line" 
                      :percentage="calculateProgress(item)" 
                      :status="getProgressStatus(item)"
                      :color="getProgressColor(item)"
                      :height="3" 
                      :show-indicator="false"
                      :border-radius="0"
                      :processing="calculateProgress(item) < 100"
                    />
                  </div>

                  <!-- 底部按钮 -->
                  <div class="card-actions">
                    <n-tooltip v-if="hasMissing(item)">
                      <template #trigger>
                        <n-button
                          quaternary
                          circle
                          type="warning"
                          @click.stop="() => openMissingInfoModal(item)"
                        >
                          <template #icon><n-icon :component="EyeIcon" /></template>
                        </n-button>
                      </template>
                      {{ getMissingCountText(item) }} (点击查看详情)
                    </n-tooltip>

                    <n-tooltip>
                      <template #trigger>
                        <n-button
                          quaternary
                          circle
                          :loading="refreshingItems[item.parent_tmdb_id]" 
                          @click.stop="() => triggerSingleRefresh(item.parent_tmdb_id, item.item_name)"
                        >
                          <template #icon><n-icon :component="SyncOutline" /></template>
                        </n-button>
                      </template>
                      立即刷新此剧集
                    </n-tooltip>

                    <n-tooltip>
                      <template #trigger>
                        <n-button 
                          quaternary 
                          circle 
                          :type="item.enable_mp_subscribe !== false ? 'primary' : 'default'" 
                          @click.stop="() => saveMpSubscribe(item, item.enable_mp_subscribe === false)"
                        >
                          <template #icon><n-icon :component="PaperPlaneIcon" /></template>
                        </n-button>
                      </template>
                      {{ item.enable_mp_subscribe !== false ? 'MoviePilot 自动订阅：已开启 (点击关闭)' : 'MoviePilot 自动订阅：已关闭 (点击开启)' }}
                    </n-tooltip>

                    <!-- A. 追剧中视图：显示强制完结按钮 -->
                    <n-tooltip v-if="currentView === 'inProgress'">
                      <template #trigger>
                        <n-button 
                          quaternary 
                          circle 
                          @click.stop="() => forceEndSingleItem(item)"
                        >
                          <template #icon>
                            <!-- 💡 按钮保持普通 quaternary，直接染红图标 -->
                            <n-icon :component="ForceEndIcon" style="color: #d03050;" />
                          </template>
                        </n-button>
                      </template>
                      强制完结此季
                    </n-tooltip>

                    <!-- B. 已完结视图：显示重新追剧按钮 -->
                    <n-tooltip v-if="currentView === 'completed'">
                      <template #trigger>
                        <n-button 
                          quaternary 
                          circle 
                          @click.stop="() => updateStatus(item.tmdb_id, 'Watching')"
                        >
                          <template #icon>
                            <!-- 💡 按钮保持普通 quaternary，直接染绿图标 -->
                            <n-icon :component="WatchingIcon" style="color: #18a058;" />
                          </template>
                        </n-button>
                      </template>
                      重新追剧
                    </n-tooltip>
                  </div>
                </div>
              </div>
              <!-- 布局结束 -->

            </n-card>
          </div>
        </div>
        <!-- Grid 结束 -->

        <div ref="loaderRef" class="loader-trigger">
          <n-spin v-if="hasMore" size="small" />
        </div>
      </div>
      <div v-else class="center-container"><n-empty :description="emptyStateDescription" size="huge" /></div>
    </div>
    
    <!-- 模态框: 缺失详情 -->
    <n-modal v-model:show="showModal" preset="card" style="width: 90%; max-width: 900px;" :title="selectedSeries ? `缺失详情 - ${selectedSeries.item_name}` : ''" :bordered="false" size="huge">
      <div v-if="selectedSeries && missingData">
        <n-tabs type="line" animated v-model:value="activeTab">
          <n-tab-pane name="seasons" :tab="`缺季 (${missingData.missing_seasons.length})`" :disabled="missingData.missing_seasons.length === 0">
            <n-list bordered>
              <n-list-item v-for="season in missingData.missing_seasons" :key="season.season_number">
                <template #prefix><n-tag type="warning">S{{ season.season_number }}</n-tag></template>
                <n-ellipsis>{{ season.name }} ({{ season.episode_count }}集, {{ formatAirDate(season.air_date) }})</n-ellipsis>
              </n-list-item>
            </n-list>
          </n-tab-pane>
          <n-tab-pane name="gaps" :tab="`缺集的季 (${missingData.seasons_with_gaps.length})`" :disabled="missingData.seasons_with_gaps.length === 0">
            <n-list bordered>
              <n-list-item v-for="gap in missingData.seasons_with_gaps" :key="gap.season">
                <n-space vertical>
                  <div><n-tag type="error">第 {{ gap.season }} 季</n-tag> 存在分集缺失</div>
                  <n-text :depth="3">具体缺失的集号: {{ gap.missing.join(', ') }}</n-text>
                </n-space>
              </n-list-item>
            </n-list>
          </n-tab-pane>
        </n-tabs>
      </div>
    </n-modal>
    
    <!-- 追剧辅助配置模态框 -->
    <n-modal
      v-model:show="showConfigModal"
      preset="card"
      title="追剧辅助配置"
      style="width: 920px; max-width: 96vw;"
      class="custom-modal glass-modal"
      :bordered="false"
      size="huge"
    >
      <div class="assistant-settings">
        <div class="settings-layout assistant-aux-layout">
          <div class="settings-col">
            <div class="settings-card">
              <div class="setting-item">
                <div class="setting-icon"><n-icon :component="DoubanIcon" /></div>
                <div class="setting-content">
                  <div class="setting-header">
                    <div>
                      <div class="setting-label">豆瓣辅助修正集数</div>
                      <div class="setting-desc">TMDb 集数滞后或错误时，尝试从豆瓣获取总集数并锁定。</div>
                    </div>
                    <n-switch v-model:value="watchlistConfig.douban_count_correction" size="small" />
                  </div>
                </div>
              </div>
              <n-divider style="margin: 0" />
              <div class="setting-item">
                <div class="setting-icon"><n-icon :component="TimeIcon" /></div>
                <div class="setting-content">
                  <div class="setting-header">
                    <div>
                      <div class="setting-label">全量刷新回溯期</div>
                      <div class="setting-desc">已完结超过该天数的剧集仅做轻量检查。</div>
                    </div>
                    <n-input-number
                      v-model:value="watchlistConfig.revival_check_days"
                      size="small"
                      style="width: 140px"
                      :min="1"
                    >
                      <template #suffix>天</template>
                    </n-input-number>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showConfigModal = false">取消</n-button>
          <n-button type="primary" :loading="configSaving" @click="saveConfig">保存策略</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, shallowRef, triggerRef, onMounted, onBeforeUnmount, h, computed, watch } from 'vue';
import axios from 'axios';
import { NPageHeader, NDivider, NEmpty, NTag, NButton, NSpace, NIcon, useMessage, useDialog, NPopconfirm, NTooltip, NCard, NImage, NEllipsis, NSpin, NAlert, NRadioGroup, NRadioButton, NModal, NTabs, NTabPane, NList, NListItem, NCheckbox, NDropdown, NInput, NSelect, NButtonGroup, NProgress, useThemeVars, NPopover, NInputNumber, NSwitch } from 'naive-ui';
import { SyncOutline, TvOutline as TvIcon, TrashOutline as TrashIcon, EyeOutline as EyeIcon, CalendarOutline as CalendarIcon, TimeOutline as TimeIcon, PlayCircleOutline as WatchingIcon, PauseCircleOutline as PausedIcon, CheckmarkCircleOutline as CompletedIcon, ScanCircleOutline as ScanIcon, CaretDownOutline as CaretDownIcon, FlashOffOutline as ForceEndIcon, ArrowUpOutline as ArrowUpIcon, ArrowDownOutline as ArrowDownIcon, DownloadOutline as DownloadIcon, AlbumsOutline as CollectionsIcon, SettingsOutline as SettingsIcon, HourglassOutline as PendingIcon, TimerOutline as TimerIcon, RefreshCircleOutline as RefreshIcon, GitNetworkOutline as GapIcon, CloudDownloadOutline as BackfillIcon, EarthOutline as DoubanIcon, PaperPlaneOutline as PaperPlaneIcon, BanOutline as IgnoredIcon } from '@vicons/ionicons5';
import { format, parseISO } from 'date-fns';
import { useConfig } from '../composables/useConfig.js';

const TMDbIcon = () => h('svg', { xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 512 512", width: "1em", height: "1em" }, [
  h('path', { d: "M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM133.2 176.6a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zm63.3-22.4a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm74.8 108.2c-27.5-3.3-50.2-26-53.5-53.5a8 8 0 0 1 16-.6c2.3 19.3 18.8 34 38.1 31.7a8 8 0 0 1 7.4 8c-2.3.3-4.5.4-6.8.4zm-74.8-108.2a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm149.7 22.4a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zM133.2 262.6a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zm63.3-22.4a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm74.8 108.2c-27.5-3.3-50.2-26-53.5-53.5a8 8 0 0 1 16-.6c2.3 19.3 18.8 34 38.1 31.7a8 8 0 0 1 7.4 8c-2.3.3-4.5.4-6.8.4zm-74.8-108.2a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm149.7 22.4a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8z", fill: "#01b4e4" })
]);

const { configModel } = useConfig();
const message = useMessage();
const dialog = useDialog();
const props = defineProps({ taskStatus: { type: Object, required: true } });

const rawWatchlist = shallowRef([]);
const currentView = ref('inProgress');
const isLoading = ref(true);
const isBatchUpdating = ref(false);
const error = ref(null);
const showModal = ref(false);
const isAddingAll = ref(false);
const selectedSeries = ref(null);
const refreshingItems = ref({});
const isTaskRunning = computed(() => props.taskStatus.is_running);
const displayCount = ref(30);
const INCREMENT = 30;
const loaderRef = ref(null);
let observer = null;
const themeVars = useThemeVars();
const selectedItems = ref([]);
const lastSelectedIndex = ref(null);
const isBackfilling = ref(false);
const searchQuery = ref('');
const filterStatus = ref('all');
const filterMissing = ref('all');
const filterGaps = ref('all');
const sortKey = ref('last_checked_at');
const sortOrder = ref('desc');
const tempTotalEpisodes = ref(0);
const activeTab = ref('seasons');
const showConfigModal = ref(false);
const configSaving = ref(false);

const buildWatchlistConfig = (data = {}) => {
  return {
    douban_count_correction: data.douban_count_correction ?? false,
    revival_check_days: data.revival_check_days ?? 365
  };
};
const watchlistConfig = ref(buildWatchlistConfig());

const openConfigModal = async () => {
  showConfigModal.value = true;
  try {
    const { data } = await axios.get('/api/watchlist/settings');
    if (data) {
       watchlistConfig.value = buildWatchlistConfig(data);
    }
  } catch (e) {
    console.warn('获取追剧配置失败或无配置，使用默认值', e);
  }
};

const saveConfig = async () => {
  configSaving.value = true;
  try {
    const payload = { ...watchlistConfig.value };
    await axios.post('/api/watchlist/settings', payload);
    watchlistConfig.value = buildWatchlistConfig(payload);
    message.success('配置保存成功');
    showConfigModal.value = false;
  } catch (e) {
    message.error('保存失败: ' + (e.response?.data?.error || e.message));
  } finally {
    configSaving.value = false;
  }
};

const triggerBackfillTask = async () => {
  dialog.info({
    title: '补全旧季',
    content: '确定要扫描数据库并自动待订阅所有缺失的旧季吗？\n\n逻辑说明：\n1. 仅针对“非最新季”的缺失季。\n2. 仅针对“未入库”且“未忽略”的季。',
    positiveText: '确定执行',
    negativeText: '取消',
    onPositiveClick: async () => {
      isBackfilling.value = true;
      try {
        const response = await axios.post('/api/tasks/run', { task_name: 'scan_old_seasons_backfill' });
        message.success(response.data.message || '补全任务已启动！');
      } catch (err) {
        message.error(err.response?.data?.error || '启动任务失败。');
      } finally {
        isBackfilling.value = false;
      }
    }
  });
};

const hasMissingSeasons = (item) => item.missing_info?.missing_seasons?.length > 0;
const hasGaps = (item) => Array.isArray(item.missing_info?.seasons_with_gaps) && item.missing_info.seasons_with_gaps.length > 0;
const hasMissing = (item) => hasMissingSeasons(item) || hasGaps(item);

const getMissingCountText = (item) => {
  if (!hasMissing(item)) return '';
  const season_count = item.missing_info?.missing_seasons?.length || 0;
  const gaps_count = hasGaps(item) ? 1 : 0;
  let parts = [];
  if (season_count > 0) parts.push(`缺 ${season_count} 季`);
  if (gaps_count > 0) parts.push(`有分集缺失`);
  return parts.join(' | ');
};

const statusFilterOptions = [
  { label: '所有状态', value: 'all' },
  { label: '追剧中', value: 'Watching' },
  { label: '已暂停', value: 'Paused' },
  { label: '待定中', value: 'Pending' },
];
const missingFilterOptions = computed(() => {
    return [
      { label: '缺季筛选', value: 'all' },
      { label: '有缺季', value: 'yes' },
      { label: '无缺季', value: 'no' },
    ];
});
const gapsFilterOptions = [
    { label: '缺集筛选', value: 'all' },
    { label: '有缺集', value: 'yes' },
    { label: '无缺集', value: 'no' },
];
const sortKeyOptions = [
  { label: '按上次检查时间', value: 'last_checked_at' },
  { label: '按剧集名称', value: 'item_name' },
  { label: '按添加时间', value: 'added_at' },
  { label: '按发行年份', value: 'release_year' },
];

const batchActions = computed(() => {
  const removeAction = { label: '批量移除', key: 'remove', icon: () => h(NIcon, { component: TrashIcon }) };
  const enableMpAction = { label: '开启 MP 订阅', key: 'enableMp', icon: () => h(NIcon, { component: PaperPlaneIcon }) };
  const disableMpAction = { label: '关闭 MP 订阅', key: 'disableMp', icon: () => h(NIcon, { component: IgnoredIcon }) };

  if (currentView.value === 'inProgress') {
    return [
      { label: '强制完结', key: 'forceEnd', icon: () => h(NIcon, { component: ForceEndIcon }) }, 
      enableMpAction,
      disableMpAction,
      removeAction
    ];
  } else if (currentView.value === 'completed') {
    return [
      { label: '重新追剧', key: 'rewatch', icon: () => h(NIcon, { component: WatchingIcon }) }, 
      enableMpAction,
      disableMpAction,
      removeAction
    ];
  }
  return []; 
});

const filteredWatchlist = computed(() => {
  let list = rawWatchlist.value;
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    list = list.filter(item => item.item_name.toLowerCase().includes(query));
  }

  if (currentView.value === 'inProgress') {
    list = list.filter(item => ['Watching', 'Paused', 'Pending'].includes(item.status));
    if (filterStatus.value !== 'all') list = list.filter(item => item.status === filterStatus.value);
    if (filterMissing.value !== 'all') list = list.filter(item => hasMissingSeasons(item) === (filterMissing.value === 'yes'));
    if (filterGaps.value !== 'all') list = list.filter(item => hasGaps(item) === (filterGaps.value === 'yes'));
  } else if (currentView.value === 'completed') {
    const completedParentIds = new Set(list.filter(item => item.status === 'Completed').map(i => i.parent_tmdb_id));
    const seasonsToAggregate = list.filter(item => completedParentIds.has(item.parent_tmdb_id));
    const groups = {};
    
    // 3. 对所有相关季度进行遍历聚合
    seasonsToAggregate.forEach(season => {
      const pid = season.parent_tmdb_id;
      if (!groups[pid]) {
        groups[pid] = { 
          ...season, 
          item_name: season.item_name.replace(/ 第 \d+ 季$/, ''), // 去掉季号作为总标题
          collected_count: 0, // 重置计数，下面累加
          total_count: 0,     // 重置计数，下面累加
          status: season.series_status, 
          is_aggregated: true,
          seasons_contains: [], 
          seasons_missing: [],  
          seasons_airing: [],
          seasons_force_ended: []
        };
      }
      // 累加集数
      groups[pid].collected_count += (season.collected_count || 0);
      groups[pid].total_count += (season.total_count || 0);
      
      // ★★★ 分类逻辑 ★★★
      const isInLibrary = (season.collected_count > 0);
      
      if (isInLibrary) {
        // 只要在库，就算包含
        // 注意：为了避免重复显示，通常 Completed 的才放入 seasons_contains，或者全部放入
        // 根据你之前的逻辑，这里是放入所有在库的
        if (season.status === 'Completed') {
             groups[pid].seasons_contains.push(season.season_number);
        } else {
             // 如果在库但不是 Completed，通常也算 contains，但为了区分显示：
             groups[pid].seasons_contains.push(season.season_number);
        }
        
        // 2. 判断是否连载中：在库 且 状态是 Watching/Paused
        if (season.status === 'Watching' || season.status === 'Paused') {
           groups[pid].seasons_airing.push(season.season_number);
        }
      } else {
        // 3. 缺失
        groups[pid].seasons_missing.push(season.season_number);
      }

      if (season.force_ended) {
        groups[pid].seasons_force_ended.push(season.season_number);
      }
      
      // 更新时间取最新的
      if (new Date(season.last_checked_at) > new Date(groups[pid].last_checked_at)) {
        groups[pid].last_checked_at = season.last_checked_at;
      }
    });

    list = Object.values(groups);
    if (filterMissing.value !== 'all') list = list.filter(item => hasMissingSeasons(item) === (filterMissing.value === 'yes'));
    if (filterGaps.value !== 'all') list = list.filter(item => hasGaps(item) === (filterGaps.value === 'yes'));
  }

  list.sort((a, b) => {
    let valA, valB;
    switch (sortKey.value) {
      case 'item_name': valA = a.item_name || ''; valB = b.item_name || ''; return sortOrder.value === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
      case 'added_at': valA = a.added_at ? new Date(a.added_at).getTime() : 0; valB = b.added_at ? new Date(b.added_at).getTime() : 0; break;
      case 'release_year': valA = a.release_year || 0; valB = b.release_year || 0; break;
      case 'last_checked_at': default: valA = a.last_checked_at ? new Date(a.last_checked_at).getTime() : 0; valB = b.last_checked_at ? new Date(b.last_checked_at).getTime() : 0; break;
    }
    return sortOrder.value === 'asc' ? valA - valB : valB - valA;
  });

  return list;
});

const formatSeasonRange = (numbers) => {
  if (!numbers || numbers.length === 0) return '';
  // ★ 核心修复：使用 Set 强行去重
  const uniqueNumbers = [...new Set(numbers)];
  const sorted = uniqueNumbers.sort((a, b) => a - b);
  
  const ranges = [];
  let start = sorted[0], prev = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === prev + 1) prev = sorted[i];
    else { ranges.push(start === prev ? `S${start}` : `S${start}-S${prev}`); start = sorted[i]; prev = sorted[i]; }
  }
  ranges.push(start === prev ? `S${start}` : `S${start}-S${prev}`);
  return ranges.join(', ');
};

const getSeriesStatusUI = (item) => {
  const tmdbStatus = item.tmdb_status;
  const internalStatus = item.status;
  const nextEp = item.next_episode_to_air; 

  if (internalStatus === 'Pending') return { text: '待定中', type: 'info', icon: PendingIcon };
  if (internalStatus === 'Watching' || internalStatus === 'Paused') return { text: '已回归', type: 'success', icon: WatchingIcon };
  if (internalStatus === 'Completed') {
      if (tmdbStatus === 'Ended' || tmdbStatus === 'Canceled') return { text: '已完结', type: 'default', icon: CompletedIcon };
      if (['Returning Series', 'In Production', 'Planned'].includes(tmdbStatus)) {
          if (nextEp && nextEp.air_date) return { text: '待回归', type: 'warning', icon: PausedIcon };
          return { text: '已完结', type: 'default', icon: CompletedIcon };
      }
  }
  return { text: '已完结', type: 'default', icon: CompletedIcon };
};

const renderedWatchlist = computed(() => filteredWatchlist.value.slice(0, displayCount.value));
const hasMore = computed(() => displayCount.value < filteredWatchlist.value.length);
const emptyStateDescription = computed(() => {
  if (rawWatchlist.value.length > 0 && filteredWatchlist.value.length === 0) return '没有匹配当前筛选条件的剧集。';
  if (currentView.value === 'inProgress') return '追剧列表为空，快去“手动处理”页面搜索并添加你正在追的剧集吧！';
  return '还没有已完结的剧集。';
});

const missingData = computed(() => {
  const defaults = { missing_seasons: [], seasons_with_gaps: [] };
  const infoFromServer = selectedSeries.value?.missing_info;
  if (infoFromServer && !Array.isArray(infoFromServer.seasons_with_gaps)) infoFromServer.seasons_with_gaps = [];
  return { ...defaults, ...infoFromServer };
});

const nextEpisode = (item) => {
  const ep = item.next_episode_to_air;
  if (!ep) return null;
  if (ep.season_number === item.season_number) return ep;
  return null;
};

const toggleSelection = (itemId, event, index) => {
  if (!event) return;
  if (event.shiftKey && lastSelectedIndex.value !== null) {
    const start = Math.min(lastSelectedIndex.value, index);
    const end = Math.max(lastSelectedIndex.value, index);
    const idsInRange = renderedWatchlist.value.slice(start, end + 1).map(i => i.tmdb_id);
    const isCurrentlySelected = selectedItems.value.includes(itemId);
    const willSelect = !isCurrentlySelected;
    if (willSelect) {
      const newSet = new Set(selectedItems.value);
      idsInRange.forEach(id => newSet.add(id));
      selectedItems.value = Array.from(newSet);
    } else {
      selectedItems.value = selectedItems.value.filter(id => !idsInRange.includes(id));
    }
  } else {
    const idx = selectedItems.value.indexOf(itemId);
    if (idx > -1) selectedItems.value.splice(idx, 1);
    else selectedItems.value.push(itemId);
  }
  lastSelectedIndex.value = index;
};

// 🚀 新增：全选计算状态（仅针对当前经过搜索、筛选过滤后的候选列表）
const isAllSelected = computed(() => {
  return filteredWatchlist.value.length > 0 && selectedItems.value.length === filteredWatchlist.value.length;
});

// 🚀 新增：半选（模糊）状态，即已勾选部分，但没勾选完
const isIndeterminate = computed(() => {
  return selectedItems.value.length > 0 && selectedItems.value.length < filteredWatchlist.value.length;
});

// 🚀 新增：一键全选/反选事件
const handleSelectAll = () => {
  if (isAllSelected.value) {
    // 如果已经全选了，点击则一键清空
    selectedItems.value = [];
  } else {
    // 否则一键将当前过滤出来所有影视剧的 tmdb_id 填入勾选列表
    selectedItems.value = filteredWatchlist.value.map(item => item.tmdb_id);
    message.info(`已全选当前过滤列表下的 ${filteredWatchlist.value.length} 个项目`);
  }
};

const handleBatchAction = (key) => {
  const getParentIds = () => {
    const selectedItemObjects = rawWatchlist.value.filter(i => selectedItems.value.includes(i.tmdb_id));
    return [...new Set(selectedItemObjects.map(i => i.parent_tmdb_id))];
  };

  if (key === 'forceEnd') {
    const seasonIds = [...new Set(selectedItems.value)]; // 强制完结只作用于选中的季
    dialog.warning({
      title: '确认操作',
      content: `确定要将选中的 ${seasonIds.length} 个季标记为“强制完结”吗？`,
      positiveText: '确定',
      negativeText: '取消',
      onPositiveClick: async () => {
        try {
          const response = await axios.post('/api/watchlist/batch_force_end', { item_ids: seasonIds });
          message.success(response.data.message || '批量操作成功！');
          await fetchWatchlist();
          selectedItems.value = [];
        } catch (err) {
          message.error(err.response?.data?.error || '批量操作失败。');
        }
      }
    });
  } else if (key === 'rewatch') {
    const parentIds = getParentIds();
    dialog.info({
      title: '确认操作', content: `确定要将选中的 ${parentIds.length} 部剧集的状态改回“追剧中”吗？`, positiveText: '确定', negativeText: '取消',
      onPositiveClick: async () => {
        try {
          const response = await axios.post('/api/watchlist/batch_update_status', { item_ids: parentIds, new_status: 'Watching' });
          message.success(response.data.message || '批量操作成功！');
          await fetchWatchlist(); 
          selectedItems.value = [];
          currentView.value = 'inProgress'; 
        } catch (err) { message.error(err.response?.data?.error || '批量操作失败。'); }
      }
    });
  } else if (key === 'remove') {
    const parentIds = getParentIds();
    dialog.warning({
      title: '确认移除', content: `确定要从追剧列表中移除选中的 ${parentIds.length} 个项目吗？此操作不可恢复。`, positiveText: '确定移除', negativeText: '取消',
      onPositiveClick: async () => {
        try {
          const response = await axios.post('/api/watchlist/batch_remove', { item_ids: parentIds });
          message.success(response.data.message || '批量移除成功！');
          await fetchWatchlist();
          selectedItems.value = [];
        } catch (err) { message.error(err.response?.data?.error || '批量移除失败。'); }
      }
    });
  // 🚀 新增：批量“开启/关闭 MP 订阅”的处理逻辑
  } else if (key === 'enableMp' || key === 'disableMp') {
    const parentIds = getParentIds();
    const enabled = (key === 'enableMp');
    
    dialog.info({
      title: '批量操作确认',
      content: `确定要将选中的 ${parentIds.length} 部剧集的 MoviePilot 自动订阅设为【${enabled ? '开启' : '关闭'}】吗？`,
      positiveText: '确定',
      negativeText: '取消',
      onPositiveClick: async () => {
        try {
          const response = await axios.post('/api/watchlist/batch_update_mp_subscribe', { 
            item_ids: parentIds, 
            enabled: enabled 
          });
          message.success(response.data.message || '批量修改配置成功！');
          
          // 💡 将更改无感同步到当前内存视图，避免刷新页面
          rawWatchlist.value.forEach(i => {
            if (parentIds.includes(i.parent_tmdb_id) || parentIds.includes(i.tmdb_id)) {
              i.enable_mp_subscribe = enabled;
            }
          });
          triggerRef(rawWatchlist);
          selectedItems.value = [];
        } catch (err) {
          message.error(err.response?.data?.error || '批量操作配置失败。');
        }
      }
    });
  }
};

const addAllSeriesToWatchlist = async () => {
  isAddingAll.value = true;
  try {
    const response = await axios.post('/api/tasks/run', { task_name: 'add-all-series-to-watchlist' });
    message.success(response.data.message || '任务已成功提交！');
  } catch (err) { message.error(err.response?.data?.error || '启动扫描任务失败。'); } 
  finally { isAddingAll.value = false; }
};

const triggerSingleRefresh = async (itemId, itemName) => {
  refreshingItems.value[itemId] = true;
  try {
    await axios.post(`/api/watchlist/refresh/${itemId}`);
    message.success(`《${itemName}》的刷新任务已提交！`);
    setTimeout(() => { fetchWatchlist(); }, 5000);
  } catch (err) { message.error(err.response?.data?.error || '启动刷新失败。'); } 
  finally { setTimeout(() => { refreshingItems.value[itemId] = false; }, 5000); }
};

watch(currentView, () => {
  displayCount.value = 30; selectedItems.value = []; lastSelectedIndex.value = null; searchQuery.value = ''; filterStatus.value = 'all'; filterMissing.value = 'all'; filterGaps.value = 'all';
});

const loadMore = () => { if (hasMore.value) displayCount.value = Math.min(displayCount.value + INCREMENT, filteredWatchlist.value.length); };

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '从未';
  try { return format(new Date(timestamp), 'MM-dd HH:mm'); } catch (e) { return 'N/A'; }
};

const formatAirDate = (dateString) => {
  if (!dateString) return '待定';
  try { return format(parseISO(dateString), 'yyyy-MM-dd'); } catch (e) { return 'N/A'; }
};

const getPosterUrl = (embyIds) => {
  const itemId = embyIds?.[0];
  if (!itemId) return '';
  return `/image_proxy/Items/${itemId}/Images/Primary?maxHeight=480&tag=1`;
};

// 🚀 新增：单体 MoviePilot 订阅开关控制（反复交替切换）
const saveMpSubscribe = async (item, enabled) => {
  try {
    const parentId = item.parent_tmdb_id || item.tmdb_id;
    await axios.post('/api/watchlist/update_mp_subscribe', { 
      tmdb_id: parentId, 
      enabled: enabled 
    });
    
    // 💡 内存状态无感刷新（更新该影视剧在当前视图下所有关联季的显示状态）
    rawWatchlist.value.forEach(i => {
      if (i.parent_tmdb_id === parentId || i.tmdb_id === parentId) {
        i.enable_mp_subscribe = enabled;
      }
    });
    triggerRef(rawWatchlist);
    
    message.success(enabled ? `已开启《${item.item_name}》的 MoviePilot 订阅同步` : `已关闭《${item.item_name}》的 MoviePilot 订阅同步`);
  } catch (err) {
    message.error('订阅状态切换失败');
  }
};

// 🚀 新增：单剧一键强制完结
const forceEndSingleItem = (item) => {
  dialog.warning({
    title: '确认强制完结',
    content: `确定要将《${item.item_name}》标记为“强制完结”吗？强制完结后它将不再被后台自动复活订阅，这不会影响同剧其它季。`,
    positiveText: '确定完结',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await axios.post('/api/watchlist/batch_force_end', { item_ids: [item.tmdb_id] });
        message.success(`《${item.item_name}》已成功标记为强制完结！`);
        await fetchWatchlist();
      } catch (err) {
        message.error(err.response?.data?.error || '操作失败。');
      }
    }
  });
};

const statusInfo = (status) => {
  const map = {
    'Watching': { type: 'success', text: '追剧中', icon: WatchingIcon, next: 'Paused', nextText: '暂停' },
    'Paused': { type: 'warning', text: '已暂停', icon: PausedIcon, next: 'Watching', nextText: '继续追' },
    'Completed': { type: 'default', text: '已完结', icon: CompletedIcon, next: 'Watching', nextText: '重新追' },
    'Pending': { type: 'info', text: '待定中', icon: PendingIcon, next: 'Watching', nextText: '强制追剧' },
  };
  return map[status] || map['Paused'];
};

const fetchWatchlist = async () => {
  isLoading.value = true; error.value = null;
  try {
    const response = await axios.get('/api/watchlist');
    rawWatchlist.value = response.data;
  } catch (err) { error.value = err.response?.data?.error || '获取追剧列表失败。'; } 
  finally { isLoading.value = false; }
};

const updateStatus = async (itemId, newStatus) => {
  const item = rawWatchlist.value.find(i => i.tmdb_id === itemId);
  if (!item) return;

  const oldStatus = item.status;
  const parentId = item.parent_tmdb_id;
  const relatedItems = rawWatchlist.value.filter(i => i.parent_tmdb_id === parentId);
  relatedItems.forEach(i => i.status = newStatus);
  triggerRef(rawWatchlist);

  try {
    await axios.post('/api/watchlist/update_status', { item_id: parentId, new_status: newStatus });
    message.success('状态更新成功！');
  } catch (err) {
    relatedItems.forEach(i => i.status = oldStatus);
    triggerRef(rawWatchlist);
    message.error(err.response?.data?.error || '更新状态失败。');
  }
};

const removeFromWatchlist = async (seriesId, itemName) => {
  try {
    await axios.post(`/api/watchlist/remove/${seriesId}`);
    message.success(`已将《${itemName}》从追剧列表移除。`);
    rawWatchlist.value = rawWatchlist.value.filter(i => i.parent_tmdb_id !== seriesId);
    selectedItems.value = []; 
  } catch (err) { message.error(err.response?.data?.error || '移除失败。'); }
};

const triggerAllWatchlistUpdate = async () => {
  isBatchUpdating.value = true;
  try {
    const response = await axios.post('/api/tasks/run', { task_name: 'process-watchlist' });
    message.success(response.data.message || '所有追剧项目更新任务已启动！');
  } catch (err) { message.error(err.response?.data?.error || '启动更新任务失败。'); } 
  finally { isBatchUpdating.value = false; }
};

const openMissingInfoModal = (item) => {
  selectedSeries.value = item;
  const info = item.missing_info || {};
  if (info.missing_seasons && info.missing_seasons.length > 0) activeTab.value = 'seasons';
  else if (info.seasons_with_gaps && info.seasons_with_gaps.length > 0) activeTab.value = 'gaps';
  else activeTab.value = 'seasons';
  showModal.value = true;
};

watch(() => props.taskStatus.is_running, (isRunning, wasRunning) => {
  if (wasRunning && !isRunning) {
    const lastAction = props.taskStatus.last_action;
    const relevantActions = ['追剧', '扫描', '刷新'];
    if (lastAction && relevantActions.some(action => lastAction.includes(action))) {
      message.info('相关后台任务已结束，正在刷新追剧列表...');
      fetchWatchlist();
    }
  }
});

const calculateProgress = (item) => {
  const total = item.total_count || 0;
  const collected = item.collected_count || 0;
  if (total === 0) return 0;
  const percent = (collected / total) * 100;
  return Math.min(percent, 100); 
};

const getProgressStatus = (item) => {
  const p = calculateProgress(item);
  if (p >= 100) return 'success';
  return 'default'; 
};

const getProgressColor = (item) => {
  const p = calculateProgress(item);
  if (p >= 100) return undefined;
  return themeVars.value.primaryColor;
};

const saveTotalEpisodes = async (item) => {
  const newTotal = tempTotalEpisodes.value || item.collected_count;
  try {
    await axios.post('/api/watchlist/update_total_episodes', { tmdb_id: item.tmdb_id, total_episodes: newTotal, item_type: 'Season' });
    message.success(`已将《${item.item_name}》总集数修正为 ${newTotal}`);
    item.total_count = newTotal;
    item.total_episodes_locked = true;
    item.show_edit_popover = false;
    triggerRef(rawWatchlist);
  } catch (err) { message.error('修正失败'); }
};

const isMobile = ref(false);
const checkMobile = () => { isMobile.value = window.innerWidth < 768; };

// 获取可用的剧集组
const fetchEpisodeGroups = async (item) => {
  // 防止重复拉取
  if (item.available_groups && item.available_groups.length > 0) return;
  
  item.loading_groups = true;
  try {
    const parentId = item.parent_tmdb_id || item.tmdb_id; // 聚合卡片和分季卡片的ID取法兜底
    const { data } = await axios.get(`/api/watchlist/episode_groups/${parentId}`);
    
    // 组装下拉框选项
    item.available_groups = data.groups.map(g => ({
      label: `${g.name} (${g.network ? g.network.name : 'Unknown'})`,
      value: g.id
    }));
    
    // 如果没有可选的
    if (item.available_groups.length === 0) {
      item.available_groups = [{ label: '暂无可用剧集组', value: 'none', disabled: true }];
    }
    
    item.saved_group_id = data.current_group_id;
    item.temp_group_id = data.current_group_id;
    
  } catch (err) {
    message.error('拉取剧集组失败');
  } finally {
    item.loading_groups = false;
  }
};

// 保存剧集组
const saveEpisodeGroup = async (item) => {
  try {
    const parentId = item.parent_tmdb_id || item.tmdb_id;
    await axios.post('/api/watchlist/set_episode_group', { 
      tmdb_id: parentId, 
      group_id: item.temp_group_id || '' 
    });
    
    message.success('已应用剧集组！后台正在执行洗牌，请稍等几十秒后刷新页面查看效果。');
    item.saved_group_id = item.temp_group_id;
    item.show_edit_popover = false; // 关闭气泡
    
  } catch (err) {
    message.error('应用剧集组失败');
  }
};

onMounted(() => {
  checkMobile(); window.addEventListener('resize', checkMobile); fetchWatchlist();
  observer = new IntersectionObserver((entries) => { if (entries[0].isIntersecting) loadMore(); }, { root: null, rootMargin: '0px', threshold: 0.1 });
  if (loaderRef.value) observer.observe(loaderRef.value);
});

onBeforeUnmount(() => { window.removeEventListener('resize', checkMobile); if (observer) observer.disconnect(); });
watch(loaderRef, (newEl, oldEl) => { if (oldEl && observer) observer.unobserve(oldEl); if (newEl && observer) observer.observe(newEl); });
</script>

<style scoped>
.center-container { display: flex; justify-content: center; align-items: center; height: calc(100vh - 200px); }

/* ★★★ 响应式 Grid 布局 ★★★ */
.responsive-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}

@media (max-width: 768px) {
  .responsive-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}

.grid-item { height: 100%; min-width: 0; }

/* ★★★ 毛玻璃卡片容器 ★★★ */
.series-card {
  cursor: pointer;
  transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
  height: 100%;
  position: relative;
  border-radius: 12px;
  overflow: hidden; 
  /* 继承全局毛玻璃属性 */
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
}

.series-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--glass-shadow) !important;
  background: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
}

.series-card :deep(.n-card__content) {
  padding: 12px !important; 
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
}

/* 内部布局：左右拉伸 */
.card-inner-layout {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
  align-items: stretch; 
  gap: 16px;
}

/* 海报区域 */
.card-poster-container {
  flex-shrink: 0; 
  width: 110px;
  height: auto; 
  min-height: 100%; 
  position: relative;
  background-color: rgba(0,0,0,0.2);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

.card-poster { width: 100%; height: 100%; display: block; }
.card-poster :deep(img) { width: 100%; height: 100%; object-fit: cover !important; display: block; }

.poster-placeholder {
  display: flex; align-items: center; justify-content: center;
  width: 100%; height: 100%; background-color: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3);
}

/* 绝对定位复选框包裹层 */
.poster-checkbox-wrap {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 10;
  background: rgba(0, 0, 0, 0.4);
  padding: 2px 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}

/* 海报底部集数遮罩 */
.poster-overlay {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.8), transparent);
  padding: 20px 8px 8px 8px;
  display: flex; justify-content: center; align-items: flex-end;
}
.episode-count {
  background: rgba(0,0,0,0.6); color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; backdrop-filter: blur(4px);
}

/* 内容区域 */
.card-content-container {
  flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; min-width: 0; padding: 0;
}

.card-header {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px;
}

.card-title {
  font-weight: 600; font-size: 1.1rem; line-height: 1.3; color: var(--text-primary);
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.card-status-area { flex-grow: 1; display: flex; flex-direction: column; gap: 6px; }
.info-line { font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
.info-line-text { color: var(--text-secondary); }
.success-text .info-line-text { color: var(--n-success-color); }
.error-text .info-line-text { color: var(--n-error-color); }

/* 底部按钮区域 */
.card-actions {
  margin-top: auto; 
  padding-top: 10px; 
  border-top: 1px dashed var(--glass-border);
  display: flex; 
  justify-content: space-evenly;
  align-items: center; 
  width: 100%; /* 确保占满容器宽度 */
}

/* 放大所有底部文本按钮里的图标 */
.card-actions .n-button {
  font-size: 20px;
  display: flex;
  justify-content: center;
}

/* ★★★ 策略配置模态框专属样式 ★★★ */
.settings-layout {
  display: flex;
  gap: 32px;
}

.settings-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.settings-group-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--n-text-color);
  border-left: 4px solid var(--n-primary-color, #18a058);
  padding-left: 10px;
  margin-bottom: 4px;
  line-height: 1.2;
}

.settings-card {
  border-radius: 8px;
  padding: 0 16px;
}

.assistant-settings {
  padding: 2px 0;
}
.assistant-hero {
  display: flex;
  gap: 16px;
  padding: 18px;
  margin-bottom: 18px;
  border-radius: 8px;
}
.assistant-section {
  padding: 16px;
}
.assistant-section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
}
.assistant-wide-control {
  margin-top: 12px;
}
.assistant-wide-control :deep(.n-dynamic-tags) {
  width: 100%;
}

.setting-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 0;
}

.setting-icon {
  font-size: 26px;
  color: var(--n-primary-color, #18a058);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
  background: rgba(128, 128, 128, 0.1);
  width: 44px;
  height: 44px;
  border-radius: 10px;
}

.setting-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.setting-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.setting-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--n-text-color);
}

.setting-desc {
  font-size: 13px;
  color: var(--n-text-color-depth-3);
  line-height: 1.5;
}

.assistant-wiki-link {
  margin-left: 8px;
  text-decoration: none;
  font-weight: 600;
}
.assistant-wiki-link:hover {
  text-decoration: underline;
}

.setting-sub-panel {
  margin-top: 10px;
  background-color: rgba(128, 128, 128, 0.05);
  border: 1px solid var(--n-border-color);
  border-radius: 6px;
  padding: 12px 16px;
}

.auto-pending-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.auto-pending-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sub-label {
  font-size: 13px;
  color: var(--n-text-color-depth-2);
}

/* 洗版订阅子选项 */
.resub-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed var(--n-border-color);
}
.resub-label {
  font-size: 13px;
  color: var(--n-text-color-depth-2);
}

.assistant-aux-layout {
  grid-template-columns: minmax(0, 1fr);
}

/* 🚀 新增：标题悬停高亮跳转效果 */
.click-title a {
  transition: color 0.2s ease-in-out;
}
.click-title a:hover {
  color: var(--n-primary-color) !important;
  text-shadow: 0 0 2px rgba(24, 160, 88, 0.2);
}

/* 策略配置：移动端响应式 */
@media (max-width: 768px) {
  .settings-layout {
    flex-direction: column;
    gap: 24px;
  }
  .settings-group-title {
    margin-top: 12px;
  }
  .settings-col .settings-group-title:first-child {
    margin-top: 0;
  }
  .auto-pending-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .setting-item {
    gap: 12px;
    padding: 14px 0;
  }
  .setting-icon {
    font-size: 22px;
    width: 38px;
    height: 38px;
    border-radius: 8px;
  }
  .settings-layout {
    grid-template-columns: 1fr;
    gap: 16px;
  }
  .assistant-hero,
  .setting-item {
    padding: 14px;
  }
}
</style>