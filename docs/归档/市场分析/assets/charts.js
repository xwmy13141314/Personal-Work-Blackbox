// assets/charts.js — 职迹 WorkTrace 优化分析报告图表
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim() || '#0969da';
  var accent2 = style.getPropertyValue('--accent2').trim() || '#cf222e';
  var ink = style.getPropertyValue('--ink').trim() || '#1f2328';
  var muted = style.getPropertyValue('--muted').trim() || '#656d76';
  var rule = style.getPropertyValue('--rule').trim() || '#d0d7de';
  var bg2 = style.getPropertyValue('--bg2').trim() || '#f6f8fa';
  var success = style.getPropertyValue('--success').trim() || '#1a7f37';
  var warn = style.getPropertyValue('--warn').trim() || '#bf8700';
  var font = style.getPropertyValue('--font').trim() || 'sans-serif';

  var charts = [];

  // ==================== Chart 1: Quality Radar ====================
  var radarEl = document.getElementById('chart-radar');
  if (radarEl) {
    var chart1 = echarts.init(radarEl, null, { renderer: 'svg' });
    chart1.setOption({
      animation: false,
      tooltip: { appendToBody: true },
      legend: {
        data: ['v3.2.0 修复后', '修复前'],
        bottom: 0,
        textStyle: { color: ink, fontSize: 12, fontFamily: font },
        itemGap: 30,
      },
      radar: {
        indicator: [
          { name: '安全性', max: 10 },
          { name: '线程安全', max: 10 },
          { name: '隐私过滤', max: 10 },
          { name: '功能完整度', max: 10 },
          { name: '用户体验', max: 10 },
          { name: '代码质量', max: 10 },
          { name: '文档完善度', max: 10 },
          { name: '市场准备度', max: 10 },
        ],
        center: ['50%', '52%'],
        radius: '65%',
        axisName: { color: ink, fontSize: 12, fontFamily: font },
        splitLine: { lineStyle: { color: rule } },
        splitArea: { areaStyle: { color: [bg2, '#fff'] } },
        axisLine: { lineStyle: { color: rule } },
      },
      series: [
        {
          type: 'radar',
          data: [
            {
              value: [7, 9, 8, 7, 7, 8, 7, 4],
              name: 'v3.2.0 修复后',
              areaStyle: { color: 'rgba(9,105,218,0.2)' },
              lineStyle: { color: accent, width: 2 },
              itemStyle: { color: accent },
              symbolSize: 6,
            },
            {
              value: [3, 4, 5, 6, 5, 5, 4, 2],
              name: '修复前',
              areaStyle: { color: 'rgba(101,109,118,0.12)' },
              lineStyle: { color: muted, width: 1.5, type: 'dashed' },
              itemStyle: { color: muted },
              symbolSize: 5,
            },
          ],
        },
      ],
    });
    charts.push(chart1);
  }

  // ==================== Chart 2: Market Growth ====================
  var marketEl = document.getElementById('chart-market');
  if (marketEl) {
    var chart2 = echarts.init(marketEl, null, { renderer: 'svg' });
    chart2.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        trigger: 'axis',
        formatter: function (params) {
          var p = params[0];
          return p.name + ' 年<br/>市场规模: <b>' + p.value + '</b> 亿美元';
        },
      },
      grid: { left: 60, right: 30, top: 30, bottom: 40 },
      xAxis: {
        type: 'category',
        data: ['2024', '2025', '2026', '2027', '2028', '2029', '2030', '2031', '2032'],
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted, fontSize: 11, fontFamily: font },
      },
      yAxis: {
        type: 'value',
        name: '亿美元',
        nameTextStyle: { color: muted, fontSize: 11, fontFamily: font },
        axisLine: { show: false },
        axisLabel: { color: muted, fontSize: 11, fontFamily: font },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      },
      series: [
        {
          type: 'bar',
          data: [3.3, 3.8, 4.4, 5.2, 6.0, 7.0, 8.2, 9.5, 11.5],
          barWidth: '55%',
          itemStyle: {
            color: function (params) {
              var colorList = [
                '#bbdffb', '#a3d4f9', '#8ac9f7', '#71bef5',
                '#58b3f3', '#3fa8f1', '#269def', '#0d92ed', accent,
              ];
              return colorList[params.dataIndex];
            },
            borderRadius: [4, 4, 0, 0],
          },
          label: {
            show: true,
            position: 'top',
            color: ink,
            fontSize: 10,
            fontFamily: font,
            formatter: '{c}',
          },
        },
        {
          type: 'line',
          data: [3.3, 3.8, 4.4, 5.2, 6.0, 7.0, 8.2, 9.5, 11.5],
          smooth: true,
          lineStyle: { color: accent2, width: 2 },
          itemStyle: { color: accent2 },
          symbolSize: 6,
          tooltip: { show: false },
        },
      ],
    });
    charts.push(chart2);
  }

  // ==================== Chart 3: Competitor Matrix (Heatmap) ====================
  var compEl = document.getElementById('chart-competitor');
  if (compEl) {
    var chart3 = echarts.init(compEl, null, { renderer: 'svg' });
    var compProducts = ['WorkTrace', 'ActivityWatch', 'RescueTime', 'Toggl Track', 'Timely', '域智盾', 'Spyrix'];
    var compFeatures = ['键盘记录', 'AI 分析', '隐私过滤', '本地存储', '免费使用', '开源', '跨平台'];
    var compData = [];
    // 0=无, 1=部分, 2=有
    var matrix = [
      [2, 2, 2, 2, 2, 1, 0], // WorkTrace
      [0, 0, 0, 2, 2, 2, 2], // ActivityWatch
      [0, 1, 0, 0, 0, 0, 2], // RescueTime
      [0, 0, 0, 0, 1, 0, 2], // Toggl Track
      [0, 2, 1, 0, 0, 0, 2], // Timely
      [2, 0, 0, 1, 0, 0, 0], // 域智盾
      [2, 0, 0, 1, 1, 0, 0], // Spyrix
    ];
    for (var i = 0; i < compProducts.length; i++) {
      for (var j = 0; j < compFeatures.length; j++) {
        compData.push([j, i, matrix[i][j]]);
      }
    }
    chart3.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (params) {
          var valMap = ['无', '部分', '有'];
          return compProducts[params.value[1]] + ' · ' + compFeatures[params.value[0]] + ': <b>' + valMap[params.value[2]] + '</b>';
        },
      },
      grid: { left: 110, right: 30, top: 20, bottom: 50 },
      xAxis: {
        type: 'category',
        data: compFeatures,
        splitArea: { show: true },
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: ink, fontSize: 11, fontFamily: font },
      },
      yAxis: {
        type: 'category',
        data: compProducts,
        splitArea: { show: true },
        axisLine: { lineStyle: { color: rule } },
        axisLabel: {
          color: function (val) {
            return val === 'WorkTrace' ? accent : ink;
          },
          fontSize: 11,
          fontFamily: font,
          fontWeight: function (val) {
            return val === 'WorkTrace' ? 'bold' : 'normal';
          },
        },
      },
      visualMap: {
        min: 0,
        max: 2,
        show: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemWidth: 15,
        itemHeight: 80,
        textStyle: { color: muted, fontSize: 10, fontFamily: font },
        inRange: { color: ['#ffebe9', '#fff8c5', '#dafbe1'] },
        text: ['有', '无'],
        calculable: false,
      },
      series: [
        {
          type: 'heatmap',
          data: compData,
          label: {
            show: true,
            formatter: function (params) {
              var valMap = ['—', '半', '✓'];
              return valMap[params.value[2]];
            },
            color: ink,
            fontSize: 13,
            fontFamily: font,
            fontWeight: 'bold',
          },
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
          },
        },
      ],
    });
    charts.push(chart3);
  }

  // ==================== Chart 4: Positioning Quadrant (Scatter) ====================
  var posEl = document.getElementById('chart-positioning');
  if (posEl) {
    var chart4 = echarts.init(posEl, null, { renderer: 'svg' });
    chart4.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (params) {
          return params.data.name + '<br/>隐私保护: ' + params.data.value[0] + '/10<br/>智能分析: ' + params.data.value[1] + '/10';
        },
      },
      grid: { left: 60, right: 40, top: 30, bottom: 50 },
      xAxis: {
        type: 'value',
        name: '隐私保护 →',
        nameLocation: 'middle',
        nameGap: 30,
        nameTextStyle: { color: muted, fontSize: 12, fontFamily: font },
        min: 0,
        max: 10,
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted, fontSize: 10, fontFamily: font },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      },
      yAxis: {
        type: 'value',
        name: '智能分析能力 →',
        nameLocation: 'middle',
        nameGap: 40,
        nameTextStyle: { color: muted, fontSize: 12, fontFamily: font },
        min: 0,
        max: 10,
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted, fontSize: 10, fontFamily: font },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      },
      series: [
        {
          type: 'scatter',
          symbolSize: function (data) {
            return data.size || 20;
          },
          data: [
            { name: 'WorkTrace', value: [9, 8], size: 32, itemStyle: { color: accent }, label: { show: true, formatter: 'WorkTrace', position: 'right', color: accent, fontSize: 12, fontWeight: 'bold', fontFamily: font } },
            { name: 'ActivityWatch', value: [8, 2], size: 22, itemStyle: { color: success }, label: { show: true, formatter: 'ActivityWatch', position: 'right', color: success, fontSize: 11, fontFamily: font } },
            { name: 'RescueTime', value: [3, 5], size: 22, itemStyle: { color: '#8b949e' }, label: { show: true, formatter: 'RescueTime', position: 'right', color: '#8b949e', fontSize: 11, fontFamily: font } },
            { name: 'Toggl Track', value: [2, 1], size: 20, itemStyle: { color: '#8b949e' }, label: { show: true, formatter: 'Toggl', position: 'right', color: '#8b949e', fontSize: 11, fontFamily: font } },
            { name: 'Timely', value: [3, 9], size: 24, itemStyle: { color: accent2 }, label: { show: true, formatter: 'Timely', position: 'right', color: accent2, fontSize: 11, fontFamily: font } },
            { name: '域智盾', value: [2, 3], size: 20, itemStyle: { color: '#8b949e' }, label: { show: true, formatter: '域智盾', position: 'right', color: '#8b949e', fontSize: 11, fontFamily: font } },
            { name: 'Spyrix', value: [1, 1], size: 18, itemStyle: { color: muted }, label: { show: true, formatter: 'Spyrix', position: 'right', color: muted, fontSize: 11, fontFamily: font } },
          ],
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: rule, type: 'dashed', width: 1 },
            data: [
              { xAxis: 5, label: { show: false } },
              { yAxis: 5, label: { show: false } },
            ],
          },
          markArea: {
            silent: true,
            itemStyle: { color: 'rgba(9,105,218,0.04)' },
            data: [[{ xAxis: 5 }, { xAxis: 10 }, { yAxis: 5 }, { yAxis: 10 }]],
          },
        },
      ],
    });
    charts.push(chart4);
  }

  // ==================== Chart 5: Launch Timeline (Gantt) ====================
  var tlEl = document.getElementById('chart-timeline');
  if (tlEl) {
    var chart5 = echarts.init(tlEl, null, { renderer: 'svg' });
    var phases = [
      { name: '发布前准备', start: 0, end: 2, color: accent2 },
      { name: '内测与发布', start: 2, end: 3, color: warn },
      { name: '增长与变现', start: 3, end: 9, color: accent },
      { name: '生态扩展', start: 6, end: 18, color: success },
    ];
    var timelineData = phases.map(function (p, idx) {
      return {
        name: p.name,
        value: [idx, p.start, p.end],
        itemStyle: { color: p.color, borderRadius: 4 },
      };
    });
    chart5.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (params) {
          var d = params.data;
          return d.name + '<br/>第 ' + d.value[1] + ' 月 - 第 ' + d.value[2] + ' 月（' + (d.value[2] - d.value[1]) + ' 个月）';
        },
      },
      grid: { left: 110, right: 40, top: 20, bottom: 40 },
      xAxis: {
        type: 'value',
        name: '月份',
        nameLocation: 'middle',
        nameGap: 28,
        nameTextStyle: { color: muted, fontSize: 11, fontFamily: font },
        min: 0,
        max: 18,
        interval: 3,
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted, fontSize: 10, fontFamily: font },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: phases.map(function (p) { return p.name; }),
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: ink, fontSize: 12, fontFamily: font, fontWeight: 'bold' },
      },
      series: [
        {
          type: 'custom',
          renderItem: function (params, api) {
            var catIdx = api.value(0);
            var start = api.coord([api.value(1), catIdx]);
            var end = api.coord([api.value(2), catIdx]);
            var height = api.size([0, 1])[1] * 0.5;
            return {
              type: 'rect',
              shape: {
                x: start[0],
                y: start[1] - height / 2,
                width: end[0] - start[0],
                height: height,
                r: 4,
              },
              style: api.style(),
            };
          },
          encode: { x: [1, 2], y: 0 },
          data: timelineData,
          label: {
            show: true,
            position: 'inside',
            color: '#fff',
            fontSize: 11,
            fontFamily: font,
            fontWeight: 'bold',
            formatter: function (params) {
              return (params.value[2] - params.value[1]) + ' 个月';
            },
          },
        },
      ],
    });
    charts.push(chart5);
  }

  // ==================== Resize Listener ====================
  window.addEventListener('resize', function () {
    charts.forEach(function (c) { c.resize(); });
  });
})();
