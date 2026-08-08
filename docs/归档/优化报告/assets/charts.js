(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var warn = style.getPropertyValue('--warn').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var p0 = style.getPropertyValue('--p0').trim();
  var p1 = style.getPropertyValue('--p1').trim();
  var p2 = style.getPropertyValue('--p2').trim();
  var p3 = style.getPropertyValue('--p3').trim();
  var success = style.getPropertyValue('--success').trim();

  // ========== Chart 1: Quality Radar ==========
  var radarEl = document.getElementById('chart-radar');
  if (radarEl) {
    var radar = echarts.init(radarEl, null, { renderer: 'svg' });
    radar.setOption({
      animation: false,
      tooltip: { appendToBody: true },
      radar: {
        indicator: [
          { name: '架构设计', max: 10 },
          { name: 'AI 容错', max: 10 },
          { name: '线程安全', max: 10 },
          { name: '数据安全', max: 10 },
          { name: '隐私保护', max: 10 },
          { name: '错误处理', max: 10 },
          { name: '测试覆盖', max: 10 },
          { name: '文档一致', max: 10 }
        ],
        center: ['50%', '52%'],
        radius: '68%',
        axisName: {
          color: ink,
          fontSize: 12,
          fontWeight: 600
        },
        splitLine: { lineStyle: { color: rule } },
        splitArea: { areaStyle: { color: [bg2, '#ffffff'] } },
        axisLine: { lineStyle: { color: rule } }
      },
      series: [{
        type: 'radar',
        data: [{
          value: [7.0, 8.5, 2.5, 3.5, 6.0, 4.5, 4.0, 4.5],
          name: '当前评分',
          areaStyle: { color: accent + '33' },
          lineStyle: { color: accent, width: 2 },
          itemStyle: { color: accent },
          symbolSize: 6,
          label: {
            show: true,
            formatter: function(p) { return p.value; },
            color: ink,
            fontSize: 11,
            fontWeight: 700
          }
        }]
      }]
    });
    window.addEventListener('resize', function() { radar.resize(); });
  }

  // ========== Chart 2: Thread Concurrency Heatmap ==========
  var threadsEl = document.getElementById('chart-threads');
  if (threadsEl) {
    var threads = echarts.init(threadsEl, null, { renderer: 'svg' });
    var threadNames = ['键盘线程', '窗口轮询', '剪贴板线程', '空闲检测', '超时检查', '报告生成'];
    var resources = ['InputBuffer', 'SessionManager', 'Database', 'WindowTracker', 'PrivacyFilter'];
    var heatData = [
      [0, 0, 1], [0, 0, 1], [0, 1, 1], [0, 3, 0], [0, 2, 0],
      [1, 0, 2], [1, 1, 2], [1, 2, 2], [1, 3, 2], [1, 4, 1],
      [2, 1, 1], [2, 2, 2], [2, 3, 1], [2, 4, 1],
      [3, 0, 2], [3, 1, 2], [3, 2, 1], [3, 3, 1],
      [4, 0, 1],
      [5, 2, 1]
    ];
    // expand to full grid
    var fullHeat = [];
    threadNames.forEach(function(_, ti) {
      resources.forEach(function(_, ri) {
        var found = heatData.find(function(d) { return d[0]===ti && d[1]===ri; });
        fullHeat.push([ri, ti, found ? found[2] : '-']);
      });
    });
    threads.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function(p) {
          var accessTypes = {1: '读取', 2: '读写', '-': '无访问'};
          return threadNames[p.value[1]] + ' → ' + resources[p.value[0]] + '<br/>访问: ' + (accessTypes[p.value[2]] || '无');
        }
      },
      grid: { top: 30, bottom: 50, left: 90, right: 30 },
      xAxis: {
        type: 'category',
        data: resources,
        splitArea: { show: false },
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: ink, fontSize: 11, fontWeight: 600, rotate: 0 }
      },
      yAxis: {
        type: 'category',
        data: threadNames,
        splitArea: { show: false },
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: ink, fontSize: 11 }
      },
      visualMap: {
        min: 0, max: 2,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 5,
        itemWidth: 14, itemHeight: 100,
        inRange: { color: [bg2, warn, p0] },
        text: ['读写', '无访问'],
        textStyle: { color: muted, fontSize: 11 }
      },
      series: [{
        type: 'heatmap',
        data: fullHeat,
        label: {
          show: true,
          formatter: function(p) {
            var labels = {1: '读', 2: '读写', '-': '-'};
            return labels[p.value[2]] || '-';
          },
          color: ink,
          fontSize: 10,
          fontWeight: 600
        },
        itemStyle: {
          borderColor: '#ffffff',
          borderWidth: 2
        },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.3)' } }
      }]
    });
    window.addEventListener('resize', function() { threads.resize(); });
  }

  // ========== Chart 3: Test Coverage ==========
  var coverageEl = document.getElementById('chart-coverage');
  if (coverageEl) {
    var coverage = echarts.init(coverageEl, null, { renderer: 'svg' });
    coverage.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        trigger: 'axis',
        axisPointer: { type: 'shadow' }
      },
      legend: {
        data: ['已测试', '未测试'],
        top: 5,
        textStyle: { color: muted, fontSize: 12 }
      },
      grid: { top: 45, bottom: 60, left: 130, right: 30 },
      xAxis: {
        type: 'value',
        name: '代码行数',
        nameTextStyle: { color: muted, fontSize: 11 },
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      yAxis: {
        type: 'category',
        data: ['personal_recorder/', 'src/ui/', 'src/main.py', 'src/ai/', 'src/collector/', 'src/storage/', 'src/processor/', 'src/config/'],
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: ink, fontSize: 11 }
      },
      series: [
        {
          name: '已测试',
          type: 'bar',
          stack: 'total',
          itemStyle: { color: success },
          barWidth: 18,
          data: [0, 0, 0, 968, 0, 604, 409, 153]
        },
        {
          name: '未测试',
          type: 'bar',
          stack: 'total',
          itemStyle: { color: p0 },
          barWidth: 18,
          label: {
            show: true,
            position: 'right',
            formatter: function(p) {
              return p.value > 0 ? p.value + ' 行' : '';
            },
            color: muted,
            fontSize: 10
          },
          data: [2352, 1206, 613, 0, 434, 0, 0, 0]
        }
      ]
    });
    window.addEventListener('resize', function() { coverage.resize(); });
  }

})();
