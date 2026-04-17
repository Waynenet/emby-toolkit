<template>
  <div content-style="padding: 24px;">
    <n-spin :show="isLoading">
      <div class="cover-generator-config">
        <n-page-header>
          <template #title>媒体库封面生成</template>
          <template #extra>
            <n-space>
              <n-button @click="runGenerateAllTask" :loading="isGenerating">
                <template #icon><n-icon :component="ImagesIcon" /></template>
                立即生成所有封面
              </n-button>
              <n-button type="primary" @click="saveConfig" :loading="isSaving">
                <template #icon><n-icon :component="SaveIcon" /></template>
                保存设置
              </n-button>
            </n-space>
          </template>
          <n-alert title="操作提示" type="info" style="margin-top: 24px;">
          本功能提取自MP插件，感谢作者<a
                  href="https://github.com/justzerock/MoviePilot-Plugins/"
                  target="_blank"
                  style="font-size: 0.85em; margin-left: 8px; color: var(--n-primary-color); text-decoration: underline;"
                >justzerock</a><br />
          开启监控新入库可实时生成封面，包括原生媒体库、自建合集。如需自定义图片，可以在【其他设置】里填写自定义路径，例如：/config/custom_images。<br />
          然后在这个目录下新建想要自定义图片的媒体库子目录，例如：/config/custom_images/漫威宇宙，在这个目录下放入以1.jpg、2.jpg...命名的图片。
          </n-alert>
        </n-page-header>

        <n-card class="content-card, dashboard-card" style="margin-top: 24px;">
          <template #header><span class="card-title">基础设置</span></template>
          <n-grid :cols="5" :x-gap="24" :y-gap="16" responsive="screen">
            <n-gi><n-form-item label="启用"><n-switch v-model:value="configData.enabled" /></n-form-item></n-gi>
            <n-gi><n-form-item label="监控新入库"><n-switch v-model:value="configData.transfer_monitor" /><template #feedback>入库后自动更新</template></n-form-item></n-gi>
            <n-gi><n-form-item label="封面上显示角标"><n-switch v-model:value="configData.show_item_count" /><template #feedback>显示总数</template></n-form-item></n-gi>
            <n-gi><n-form-item label="封面图片排序"><n-select v-model:value="configData.sort_by" :options="sortOptions" /></n-form-item></n-gi>
            <n-gi><n-form-item label="默认分级上限"><n-select v-model:value="configData.max_safe_rating" :options="ratingLimitOptions" /></n-form-item></n-gi>

            <n-gi :span="5"><n-divider style="margin-top: 8px; margin-bottom: 8px;" /></n-gi>

            <n-gi :span="5"> 
              <n-form-item label="选择要【忽略】的媒体库">
                <n-checkbox-group v-model:value="configData.exclude_libraries" style="display: flex; flex-wrap: wrap; gap: 8px 16px;">
                  <n-checkbox v-for="lib in libraryOptions" :key="lib.value" :value="lib.value" :label="lib.label" />
                </n-checkbox-group>
              </n-form-item>
            </n-gi>
          </n-grid>
          <div v-if="configData.show_item_count" style="margin-top: 16px;">
            <n-divider /> 
            <n-grid :cols="2" :x-gap="24">
              <n-gi>
                <n-form-item label="数字样式">
                  <n-radio-group v-model:value="configData.badge_style">
                    <n-radio-button value="badge">徽章</n-radio-button>
                    <n-radio-button value="ribbon">缎带</n-radio-button>
                  </n-radio-group>
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="数字大小">
                  <n-slider v-model:value="configData.badge_size_ratio" :step="0.01" :min="0.08" :max="0.20" :format-tooltip="value => `${(value * 100).toFixed(0)}%`"/>
                </n-form-item>
              </n-gi>
            </n-grid>
          </div>
        </n-card>

        <n-card class="content-card, dashboard-card" style="margin-top: 24px;">
          <n-tabs v-model:value="configData.tab" type="line" animated>
            <n-tab-pane name="style-tab" tab="封面风格">
              <!-- ★ 8个风格：4列2行 完美排版 -->
              <n-radio-group v-model:value="configData.cover_style" name="cover-style-group" style="width: 100%;">
                <n-grid :cols="4" :x-gap="12" :y-gap="16" responsive="screen">
                  <n-gi v-for="style in styles" :key="style.value">
                    <n-card class="dashboard-card style-card" :class="{'is-active': configData.cover_style === style.value}" @click="configData.cover_style = style.value">
                      <template #cover><img :src="stylePreviews[style.previewKey]" class="style-img" /></template>
                      <n-radio :value="style.value" :label="style.title" style="margin-top: 8px; justify-content: center;" />
                    </n-card>
                  </n-gi>
                </n-grid>
              </n-radio-group>
            </n-tab-pane>

            <n-tab-pane name="title-tab" tab="封面标题">
              <n-space vertical>
                <n-grid :cols="10" :x-gap="12" style="padding: 0 8px; margin-bottom: 4px;">
                  <n-gi :span="3"><span style="font-weight: 500;">媒体库名称</span></n-gi>
                  <n-gi :span="3"><span style="font-weight: 500;">中文标题</span></n-gi>
                  <n-gi :span="3"><span style="font-weight: 500;">英文标题</span></n-gi>
                  <n-gi :span="1"></n-gi>
                </n-grid>
                <div v-for="(item, index) in titleConfigs" :key="item.id">
                  <n-grid :cols="10" :x-gap="12" :y-gap="8">
                    <n-gi :span="3"><n-input v-model:value="item.library" placeholder="完全一致" /></n-gi>
                    <n-gi :span="3"><n-input v-model:value="item.zh" placeholder="中文" /></n-gi>
                    <n-gi :span="3"><n-input v-model:value="item.en" placeholder="英文" /></n-gi>
                    <n-gi :span="1" style="display: flex; align-items: center;">
                      <n-button type="error" dashed @click="removeTitleConfig(index)"><template #icon><n-icon :component="TrashIcon" /></template></n-button>
                    </n-gi>
                  </n-grid>
                </div>
                <n-button @click="addTitleConfig" type="primary" dashed style="margin-top: 16px;">
                  <template #icon><n-icon :component="AddIcon" /></template>新增配置
                </n-button>
              </n-space>
            </n-tab-pane>

            <n-tab-pane name="single-tab" tab="单图风格设置">
              <n-alert type="info" :bordered="false" style="margin-bottom: 20px;">
                单图风格的通用设置。
              </n-alert>
              <n-grid :cols="2" :x-gap="24" :y-gap="12" responsive="screen">
                <n-gi><n-form-item label="中文字体（本地路径）"><n-input v-model:value="configData.zh_font_path_local" placeholder="留空使用预设" /></n-form-item></n-gi>
                <n-gi><n-form-item label="英文字体（本地路径）"><n-input v-model:value="configData.en_font_path_local" placeholder="留空使用预设" /></n-form-item></n-gi>
                <n-gi><n-form-item label="中文字体（下载链接）"><n-input v-model:value="configData.zh_font_url" placeholder="留空使用预设" /></n-form-item></n-gi>
                <n-gi><n-form-item label="英文字体（下载链接）"><n-input v-model:value="configData.en_font_url" placeholder="留空使用预设" /></n-form-item></n-gi>
                <n-gi><n-form-item label="中文字体大小比例"><n-input-number v-model:value="configData.zh_font_size" :step="0.1" placeholder="1.0" /></n-form-item></n-gi>
                <n-gi><n-form-item label="英文字体大小比例"><n-input-number v-model:value="configData.en_font_size" :step="0.1" placeholder="1.0" /></n-form-item></n-gi>
                <n-gi><n-form-item label="背景模糊程度"><n-input-number v-model:value="configData.blur_size" placeholder="50" /></n-form-item></n-gi>
                <n-gi><n-form-item label="背景颜色混合占比"><n-input-number v-model:value="configData.color_ratio" :step="0.1" placeholder="0.8" /></n-form-item></n-gi>
                <n-gi><n-form-item label="优先使用海报图"><n-switch v-model:value="configData.single_use_primary" /></n-form-item></n-gi>
              </n-grid>
            </n-tab-pane>

            <n-tab-pane name="multi-1-tab" tab="多图风格设置">
              <n-grid :cols="2" :x-gap="24" :y-gap="12" responsive="screen">
                <n-gi :span="2"><n-alert type="info" :bordered="false">多图风格的通用设置。</n-alert></n-gi>
                <n-gi><n-form-item label="中文字体（本地路径）"><n-input v-model:value="configData.zh_font_path_multi_1_local" :disabled="configData.multi_1_use_main_font" /></n-form-item></n-gi>
                <n-gi><n-form-item label="英文字体（本地路径）"><n-input v-model:value="configData.en_font_path_multi_1_local" :disabled="configData.multi_1_use_main_font" /></n-form-item></n-gi>
                <n-gi><n-form-item label="中文字体（下载链接）"><n-input v-model:value="configData.zh_font_url_multi_1" :disabled="configData.multi_1_use_main_font" /></n-form-item></n-gi>
                <n-gi><n-form-item label="英文字体（下载链接）"><n-input v-model:value="configData.en_font_url_multi_1" :disabled="configData.multi_1_use_main_font" /></n-form-item></n-gi>
                <n-gi><n-form-item label="中文字体大小比例"><n-input-number v-model:value="configData.zh_font_size_multi_1" :step="0.1" placeholder="1.0" /></n-form-item></n-gi>
                <n-gi><n-form-item label="英文字体大小比例"><n-input-number v-model:value="configData.en_font_size_multi_1" :step="0.1" placeholder="1.0" /></n-form-item></n-gi>
                <n-gi><n-form-item label="背景模糊程度"><n-input-number v-model:value="configData.blur_size_multi_1" placeholder="50" :disabled="!configData.multi_1_blur" /></n-form-item></n-gi>
                <n-gi><n-form-item label="背景颜色混合占比"><n-input-number v-model:value="configData.color_ratio_multi_1" :step="0.1" placeholder="0.8" :disabled="!configData.multi_1_blur" /></n-form-item></n-gi>
                 <n-gi :span="2">
                  <n-space>
                    <n-form-item label="启用模糊背景"><n-switch v-model:value="configData.multi_1_blur" /></n-form-item>
                    <n-form-item label="使用单图风格字体"><n-switch v-model:value="configData.multi_1_use_main_font" /></n-form-item>
                    <n-form-item label="优先使用海报图"><n-switch v-model:value="configData.multi_1_use_primary" /></n-form-item>
                  </n-space>
                </n-gi>
              </n-grid>
            </n-tab-pane>

            <n-tab-pane name="others-tab" tab="其他设置">
              <n-grid :cols="2" :x-gap="24">
                <n-gi><n-form-item label="自定义图片目录（可选）"><n-input v-model:value="configData.covers_input" placeholder="/path/to/custom/images" /></n-form-item></n-gi>
                <n-gi><n-form-item label="封面另存目录（可选）"><n-input v-model:value="configData.covers_output" placeholder="/path/to/save/covers" /></n-form-item></n-gi>
              </n-grid>
            </n-tab-pane>
          </n-tabs>
        </n-card>
      </div>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import axios from 'axios';
import { 
  useMessage, NPageHeader, NButton, NIcon, NCard, NGrid, NGi, 
  NFormItem, NSwitch, NSelect, NTabs, NTabPane, NCheckboxGroup, NCheckbox, 
  NSpin, NSpace, NInput, NInputNumber, NRadioGroup, NRadioButton, NSlider, 
  NDivider, NAlert 
} from 'naive-ui';
import { SaveOutline as SaveIcon, ImagesOutline as ImagesIcon, TrashOutline as TrashIcon, AddOutline as AddIcon } from '@vicons/ionicons5';
import * as yaml from 'js-yaml'; 

import { single_1, single_2, multi_1, single_3 } from '../assets/cover_styles/images.js';
const stylePreviews = ref({ single_1: single_1, single_2: single_2, multi_1: multi_1, single_3: single_3 });

// ★ 完整 8 种样式列表
const styles = [
  { title: "单图 1 (静)", value: "single_1", previewKey: "single_1" },
  { title: "单图 2 (静)", value: "single_2", previewKey: "single_2" },
  { title: "全屏模糊 (静)", value: "single_3", previewKey: "single_3" },
  { title: "多图 1 (静)", value: "multi_1", previewKey: "multi_1" },
  { title: "卡片轮播 (动)", value: "dynamic_1", previewKey: "single_1" },
  { title: "侧面溶解 (动)", value: "dynamic_2", previewKey: "single_2" },
  { title: "全屏溶解 (动)", value: "dynamic_3", previewKey: "single_3" },
  { title: "斜向轮转 (动)", value: "dynamic_multi_1", previewKey: "multi_1" }
];

const message = useMessage();
const isLoading = ref(true);
const isSaving = ref(false);
const isGenerating = ref(false);
const configData = ref({});
const ratingLimitOptions = ref([]);
const titleConfigs = ref([]);
const libraryOptions = ref([]);

const sortOptions = [
  { label: "最新添加", value: "Latest" },
  { label: "随机", value: "Random" },
];

const parseYamlToData = (yamlString) => {
  try {
    if (!yamlString || yamlString.trim() === '') { titleConfigs.value = []; return; }
    const data = yaml.load(yamlString);
    titleConfigs.value = Object.entries(data).map(([library, titles], index) => ({
      id: Date.now() + index, library: library, zh: titles[0] || '', en: titles[1] || ''
    }));
  } catch (e) {
    titleConfigs.value = [];
  }
};

const convertDataToYaml = () => {
  try {
    const dataObject = titleConfigs.value.reduce((acc, item) => {
      if (item.library && item.library.trim() !== '') acc[item.library.trim()] = [item.zh || '', item.en || ''];
      return acc;
    }, {});
    if (Object.keys(dataObject).length === 0) return '';
    return yaml.dump(dataObject);
  } catch (e) {
    return configData.value.title_config;
  }
};

const addTitleConfig = () => { titleConfigs.value.push({ id: Date.now(), library: '', zh: '', en: '' }); };
const removeTitleConfig = (index) => { titleConfigs.value.splice(index, 1); };

const fetchConfig = async () => {
  isLoading.value = true;
  try {
    const response = await axios.get('/api/config/cover_generator');
    configData.value = response.data;
    parseYamlToData(configData.value.title_config);
  } catch (error) { message.error('加载失败'); } finally { isLoading.value = false; }
};

const fetchLibraryOptions = async () => {
  try {
    const response = await axios.get('/api/config/cover_generator/libraries');
    libraryOptions.value = response.data;
  } catch (error) {}
};

const saveConfig = async () => {
  isSaving.value = true;
  configData.value.title_config = convertDataToYaml();
  try {
    await axios.post('/api/config/cover_generator', configData.value);
    message.success('配置已成功保存！');
  } catch (error) { message.error('保存配置失败。'); } finally { isSaving.value = false; }
};

const runGenerateAllTask = async () => {
  isGenerating.value = true;
  try {
    await axios.post('/api/tasks/run', { task_name: 'generate-all-covers' });
    message.success('已触发任务');
  } catch (error) { message.error('触发任务失败'); } finally { isGenerating.value = false; }
};

const fetchRatingOptions = async () => {
  try {
    const response = await axios.get('/api/custom_collections/config/rating_mapping');
    const mapping = response.data || {};
    const valueMap = new Map();
    Object.values(mapping).forEach(rules => {
      if (Array.isArray(rules)) {
        rules.forEach(rule => {
          if (rule.emby_value !== null && rule.emby_value !== undefined && rule.label) {
            if (!valueMap.has(rule.emby_value)) valueMap.set(rule.emby_value, rule.label);
          }
        });
      }
    });
    const dynamicOptions = Array.from(valueMap.entries()).sort((a, b) => a[0] - b[0]).map(([val, label]) => ({ label: `${label} (等级 ${val})`, value: val }));
    dynamicOptions.push({ label: '无限制', value: 999 });
    ratingLimitOptions.value = dynamicOptions;
  } catch (error) {
    ratingLimitOptions.value = [{ label: '青少年', value: 8 }, { label: '无限制', value: 999 }];
  }
};

onMounted(() => {
  fetchConfig();
  fetchLibraryOptions();
  fetchRatingOptions();
});
</script>

<style scoped>
.style-card {
  cursor: pointer;
  text-align: center;
  transition: all 0.2s ease;
  border: 2px solid transparent;
}
.style-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.style-card.is-active {
  border-color: var(--n-primary-color);
  box-shadow: 0 0 0 2px rgba(24, 160, 88, 0.2);
}
.style-img {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-bottom: 1px solid #eee;
}
.n-radio {
  width: 100%;
}
</style>