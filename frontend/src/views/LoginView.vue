<script setup lang="ts">
import { ref } from 'vue'
import { ElAlert, ElButton, ElInput } from 'element-plus'
import { signIn, sessionError } from '../stores/session'
import { router } from '../router'
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')
async function submit() {
  if (busy.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请输入账号和密码'; return }
  busy.value = true
  try { await signIn(username.value.trim(), password.value); password.value = ''; await router.replace('/') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '登录失败，请重试' }
  finally { busy.value = false }
}
</script>
<template>
  <main class="login-page">
    <section class="login-story"><div class="brand"><span class="brand-mark">M</span>MeetingFlow</div><div class="login-intro"><p class="eyebrow">会议 · 行动 · 协作</p><h1>好的会议，<br>从行动开始。</h1><p>记录关键结论，明确每一项工作。<br>让团队在会议之后，依然步调一致。</p></div><div class="flow-preview"><span>01 会议记录</span><i>→</i><span>02 明确任务</span><i>→</i><span>03 跟进进展</span></div></section>
    <section class="login-panel"><form class="login-form" @submit.prevent="submit">
      <p class="eyebrow">欢迎回来</p><h2>登录工作空间</h2><p class="muted">查看会议安排与需要跟进的任务。</p>
      <ElAlert v-if="error || sessionError" :title="error || sessionError" type="error" :closable="false" show-icon />
      <label for="username">账号</label><ElInput id="username" v-model="username" name="username" autocomplete="username" placeholder="输入你的账号" size="large" :disabled="busy" />
      <label for="password">密码</label><ElInput id="password" v-model="password" name="password" type="password" autocomplete="current-password" show-password placeholder="输入密码" size="large" :disabled="busy" />
      <ElButton class="login-submit" type="primary" size="large" native-type="submit" :loading="busy">登录</ElButton>
      <p class="login-hint">演示账号：boss、zhangsan、lisi、wangwu、zhaoliu<br>请使用管理员提供的对应密码。</p>
    </form></section>
  </main>
</template>
