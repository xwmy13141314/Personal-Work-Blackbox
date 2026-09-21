import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

// 兼容 bundle / runner 两种 configLoader（runner 模式下 __dirname 未定义）
const projectDir = path.dirname(fileURLToPath(import.meta.url))

function figmaAssetResolver() {
  return {
    name: 'figma-asset-resolver',
    resolveId(id) {
      if (id.startsWith('figma:asset/')) {
        const filename = id.replace('figma:asset/', '')
        return path.resolve(projectDir, 'src/assets', filename)
      }
    },
  }
}

export default defineConfig({
  // pywebview http_server 以 index.html 父目录为 root，必须用相对路径
  base: './',
  plugins: [
    figmaAssetResolver(),
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(projectDir, './src'),
    },
  },
  build: {
    outDir: path.resolve(projectDir, '../../web_frontend'),
    emptyOutDir: true,
  },
  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
