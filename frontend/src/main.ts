import { createApp } from 'vue'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './style.css'
import { router } from './router'
import { onUnauthorized } from './api/client'
import { clearSession } from './stores/session'

onUnauthorized(() => { clearSession(); void router.replace('/login') })
createApp(App).use(router).mount('#app')
