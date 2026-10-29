import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import type ApexCharts from 'apexcharts';
import {
  ChartComponent,
  type ApexAxisChartSeries,
  type ApexOptions,
  type YAxisAnnotations,
} from 'ng-apexcharts';
import {
  PlotArea,
  nearestTime,
  niceAxisScale,
  pixelToData,
  priceRange,
} from '../../chart-geometry';
import { Candle, ChartResponse } from '../../models/market-data';
import { formatAxisTick, formatPrice, formatVolume } from '../../price-format';
import { Preferences, Theme } from '../../services/preferences';
import { chartPalette } from '../../theme-palette';

interface TrendLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface ChartWithGlobals {
  w: {
    globals: PlotArea;
  };
}

type ChartPane = 'price' | 'volume' | 'rsi';

@Component({
  selector: 'app-price-chart',
  imports: [ChartComponent, DatePipe, DecimalPipe],
  templateUrl: './price-chart.html',
  styleUrl: './price-chart.css',
})
export class PriceChart {
  readonly data = input.required<ChartResponse>();
  readonly theme = input.required<Theme>();

  private readonly preferences = inject(Preferences);

  protected readonly showSma20 = computed(() => this.preferences.chartToggles().sma20);
  protected readonly showSma50 = computed(() => this.preferences.chartToggles().sma50);
  protected readonly showRsi = computed(() => this.preferences.chartToggles().rsi);
  protected readonly showLevels = computed(() => this.preferences.chartToggles().levels);
  protected readonly drawing = signal(false);
  protected readonly pending = signal<{ x: number; y: number } | null>(null);
  protected readonly keyboardIndex = signal<number | null>(null);
  protected readonly trendLines = signal<TrendLine[]>([]);
  protected readonly chartInstance = signal<ApexCharts | null>(null);
  protected readonly volumeChartInstance = signal<ApexCharts | null>(null);
  protected readonly rsiChartInstance = signal<ApexCharts | null>(null);
  private readonly visibleRange = signal<{ min: number; max: number } | null>(null);

  protected readonly visibleCandles = computed(() => this.data().candles.slice(-12));
  protected readonly hasVolume = computed(() =>
    this.data().candles.some((candle) => (candle.v ?? 0) > 0),
  );
  private readonly maxVolume = computed(() => this.maxVolumeOf(this.data().candles));
  protected readonly hasRsi = computed(() => this.data().rsi.points.length > 0);
  protected readonly bottomChart = computed<'price' | 'volume' | 'rsi'>(() => {
    if (this.showRsi() && this.hasRsi()) {
      return 'rsi';
    }
    if (this.hasVolume()) {
      return 'volume';
    }
    return 'price';
  });
  protected readonly sourceLabel = computed(() => {
    const source = this.data().source;
    if (source === 'twelve_data') {
      return 'Twelve Data';
    }
    if (source === 'cboe_index_history') {
      return 'CBOE daily history';
    }
    return 'unavailable';
  });

  private readonly palette = computed(() => chartPalette(this.theme()));

  protected readonly hoveredIndex = signal<number | null>(null);
  protected readonly hoverLeft = signal<number | null>(null);
  protected readonly hoverPrice = signal<{
    y: number;
    value: string;
    left: number;
    width: number;
  } | null>(null);

  protected readonly activeCandle = computed<Candle | null>(() => {
    const candles = this.data().candles;
    if (candles.length === 0) {
      return null;
    }
    const index = this.hoveredIndex();
    return candles[index ?? candles.length - 1] ?? null;
  });

  protected readonly keyboardStatus = computed(() => {
    const index = this.keyboardIndex();
    const candle = index === null ? null : this.data().candles[index];
    if (!candle) {
      return '';
    }
    return `Keyboard cursor on ${candle.t}, close ${formatPrice(candle.c)}.`;
  });

  protected readonly activeValues = computed(() => {
    const candle = this.activeCandle();
    if (!candle) {
      return null;
    }
    return {
      date: candle.t,
      rising: candle.c >= candle.o,
      open: formatPrice(candle.o),
      high: formatPrice(candle.h),
      low: formatPrice(candle.l),
      close: formatPrice(candle.c),
      volume: candle.v === null ? '—' : formatVolume(candle.v),
    };
  });

  private readonly smaByTime = computed(() =>
    this.data().sma.map(
      (series) => new Map(series.points.map((point) => [new Date(point.t).getTime(), point.value])),
    ),
  );

  protected readonly activeSma = computed(() => {
    const candle = this.activeCandle();
    if (!candle) {
      return [];
    }
    const time = new Date(candle.t).getTime();
    const maps = this.smaByTime();
    const palette = this.palette();
    return this.data()
      .sma.slice(0, 2)
      .flatMap((series, index) => {
        const enabled = index === 0 ? this.showSma20() : this.showSma50();
        if (!enabled) {
          return [];
        }
        const value = maps[index]?.get(time);
        return [
          {
            period: series.period,
            value: value === undefined ? '—' : formatPrice(value),
            color: index === 0 ? palette.sma20 : palette.sma50,
          },
        ];
      });
  });

  private readonly candleTimes = computed(() =>
    this.data().candles.map((candle) => new Date(candle.t).getTime()),
  );

  private readonly initialYRange = computed(() => this.rangeFor(this.data().candles));

  protected readonly series = computed<ApexAxisChartSeries>(() => {
    const palette = this.palette();
    const entries: ApexAxisChartSeries = [
      {
        name: 'Price',
        type: 'candlestick',
        color: palette.up,
        data: this.data().candles.map((candle) => ({
          x: new Date(candle.t).getTime(),
          y: [candle.o, candle.h, candle.l, candle.c],
        })),
      },
    ];

    const sma = this.data().sma;
    if (this.showSma20() && sma[0]) {
      entries.push(this.lineSeries(`SMA ${sma[0].period}`, sma[0].points, palette.sma20));
    }
    if (this.showSma50() && sma[1]) {
      entries.push(this.lineSeries(`SMA ${sma[1].period}`, sma[1].points, palette.sma50));
    }
    this.trendLines().forEach((line, index) => {
      entries.push({
        name: `Trend ${index + 1}`,
        type: 'line',
        color: palette.trend,
        data: [
          { x: line.x1, y: line.y1 },
          { x: line.x2, y: line.y2 },
        ],
      });
    });
    return entries;
  });

  protected readonly options = computed<ApexOptions>(() => {
    const palette = this.palette();
    const initialRange = this.initialYRange();
    const times = this.candleTimes();
    return {
      chart: {
        id: 'price-chart',
        type: 'candlestick',
        height: 430,
        width: '100%',
        background: 'transparent',
        foreColor: palette.text,
        animations: { enabled: false },
        toolbar: {
          show: true,
          tools: {
            download: true,
            selection: true,
            zoom: true,
            zoomin: true,
            zoomout: true,
            pan: true,
            reset: true,
          },
        },
        zoom: { enabled: true },
        events: {
          zoomed: (_event, context) => {
            if (!context) {
              return;
            }
            this.scaleYToRange(context.xaxis.min, context.xaxis.max);
          },
          scrolled: (_event, context) => {
            if (!context) {
              return;
            }
            this.scaleYToRange(context.xaxis.min, context.xaxis.max);
          },
        },
      },
      colors: [palette.up, palette.sma20, palette.sma50, palette.rsi, palette.trend],
      theme: { mode: palette.tooltip },
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth', width: 1.5 },
      markers: { size: 0, hover: { size: 3 } },
      grid: { borderColor: palette.border, strokeDashArray: 4 },
      legend: { show: false },
      plotOptions: {
        candlestick: {
          colors: { upward: palette.up, downward: palette.down },
          wick: { useFillColor: true },
        },
      },
      xaxis: {
        type: 'datetime',
        min: times.length > 0 ? times[0] : undefined,
        max: times.length > 0 ? times[times.length - 1] : undefined,
        tickAmount: 6,
        labels: {
          show: this.bottomChart() === 'price',
          datetimeUTC: true,
          style: { colors: palette.text },
        },
        axisBorder: { color: palette.border },
        axisTicks: { color: palette.border },
      },
      yaxis: this.priceYAxis(initialRange),
      annotations: {
        yaxis: this.showLevels() ? this.levelAnnotations() : [],
      },
      tooltip: { enabled: false },
      noData: {
        text: 'No candles available',
        style: { color: palette.text },
      },
    };
  });

  protected readonly volumeSeries = computed<ApexAxisChartSeries>(() => {
    const palette = this.palette();
    return [
      {
        name: 'Volume',
        type: 'bar',
        data: this.data().candles.map((candle) => ({
          x: new Date(candle.t).getTime(),
          y: candle.v ?? 0,
          fillColor: candle.c >= candle.o ? palette.volumeUp : palette.volumeDown,
        })),
      },
    ];
  });

  protected readonly volumeOptions = computed<ApexOptions>(() => {
    const palette = this.palette();
    return {
      chart: {
        id: 'volume-chart',
        type: 'bar',
        height: 90,
        width: '100%',
        background: 'transparent',
        foreColor: palette.text,
        animations: { enabled: false },
        toolbar: { show: false },
        zoom: { enabled: false },
        parentHeightOffset: 0,
      },
      colors: [palette.up],
      theme: { mode: palette.tooltip },
      dataLabels: { enabled: false },
      stroke: { width: 0 },
      fill: { opacity: 1 },
      grid: { borderColor: palette.border, strokeDashArray: 4 },
      legend: { show: false },
      plotOptions: {
        bar: { columnWidth: '65%', borderRadius: 2 },
      },
      xaxis: {
        type: 'datetime',
        tickAmount: 6,
        labels: {
          show: this.bottomChart() === 'volume',
          datetimeUTC: true,
          style: { colors: palette.text },
        },
        axisBorder: { color: palette.border },
        axisTicks: { show: false },
      },
      yaxis: this.volumeYAxis(this.maxVolume()),
      tooltip: { enabled: false },
      noData: { text: 'No volume', style: { color: palette.text } },
    };
  });

  protected readonly rsiSeries = computed<ApexAxisChartSeries>(() => [
    {
      name: 'RSI 14',
      type: 'line',
      color: this.palette().rsi,
      data: this.data().rsi.points.map((point) => ({
        x: new Date(point.t).getTime(),
        y: point.value,
      })),
    },
  ]);

  protected readonly rsiOptions = computed<ApexOptions>(() => {
    const palette = this.palette();
    return {
      chart: {
        id: 'rsi-chart',
        type: 'line',
        height: 150,
        width: '100%',
        background: 'transparent',
        foreColor: palette.text,
        animations: { enabled: false },
        toolbar: { show: false },
        zoom: { enabled: false },
      },
      colors: [palette.rsi],
      theme: { mode: palette.tooltip },
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth', width: 1.5 },
      markers: { size: 0, hover: { size: 3 } },
      grid: { borderColor: palette.border, strokeDashArray: 4 },
      legend: { show: false },
      xaxis: {
        type: 'datetime',
        tickAmount: 6,
        labels: {
          show: this.bottomChart() === 'rsi',
          datetimeUTC: true,
          style: { colors: palette.text },
        },
        axisBorder: { color: palette.border },
        axisTicks: { color: palette.border },
      },
      yaxis: {
        min: 0,
        max: 100,
        tickAmount: 2,
        labels: {
          minWidth: 44,
          formatter: (value: number) => formatAxisTick(value, 100, 2),
          style: { colors: palette.text },
        },
      },
      annotations: {
        yaxis: [
          { y: 70, borderColor: palette.resistance },
          { y: 30, borderColor: palette.support },
        ],
      },
      tooltip: { enabled: true, theme: palette.tooltip },
    };
  });

  constructor() {
    effect(() => {
      this.data().symbol;
      this.data().range;
      this.trendLines.set([]);
      this.pending.set(null);
      this.drawing.set(false);
      this.keyboardIndex.set(null);
      this.visibleRange.set(null);
      this.clearHover();
    });
  }

  protected onChartReady(chart: ApexCharts): void {
    this.chartInstance.set(chart);
    const candles = this.data().candles;
    if (candles.length > 0) {
      const first = candles[0];
      const last = candles[candles.length - 1];
      this.scaleYToRange(new Date(first.t).getTime(), new Date(last.t).getTime());
    }
  }

  protected onVolumeReady(chart: ApexCharts): void {
    this.volumeChartInstance.set(chart);
    this.applyVisibleRange(chart);
  }

  protected onRsiReady(chart: ApexCharts): void {
    this.rsiChartInstance.set(chart);
    this.applyVisibleRange(chart);
  }

  private applyVisibleRange(chart: ApexCharts): void {
    const range = this.visibleRange();
    if (!range) {
      return;
    }
    void chart.updateOptions(
      { xaxis: { min: range.min, max: range.max } },
      false,
      false,
      false,
      false,
    );
  }

  protected toggleSma20(): void {
    this.preferences.setChartToggle('sma20', !this.showSma20());
  }

  protected toggleSma50(): void {
    this.preferences.setChartToggle('sma50', !this.showSma50());
  }

  protected toggleRsi(): void {
    this.preferences.setChartToggle('rsi', !this.showRsi());
  }

  protected toggleLevels(): void {
    this.preferences.setChartToggle('levels', !this.showLevels());
  }

  protected startDrawing(): void {
    this.drawing.update((value) => !value);
    this.pending.set(null);
    this.keyboardIndex.set(null);
  }

  protected clearLines(): void {
    this.trendLines.set([]);
    this.pending.set(null);
    this.drawing.set(false);
    this.keyboardIndex.set(null);
  }

  protected onHover(event: MouseEvent, pane: ChartPane): void {
    const instance = this.chartFor(pane);
    if (!instance) {
      return;
    }
    const globals = (instance as unknown as ChartWithGlobals).w?.globals;
    if (!globals) {
      return;
    }
    const host = event.currentTarget;
    if (!(host instanceof HTMLElement)) {
      return;
    }
    const rect = host.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const point = pixelToData(x, y, globals);
    if (!point) {
      this.clearHover();
      return;
    }
    const snapped = nearestTime(point.x, this.candleTimes());
    if (snapped === null) {
      this.clearHover();
      return;
    }
    const index = this.candleTimes().indexOf(snapped);
    if (index < 0) {
      this.clearHover();
      return;
    }
    this.hoveredIndex.set(index);
    this.hoverLeft.set(x);
    this.hoverPrice.set(
      pane === 'price'
        ? {
            y,
            value: formatPrice(point.y),
            left: globals.translateX,
            width: globals.gridWidth,
          }
        : null,
    );
  }

  protected clearHover(): void {
    this.hoveredIndex.set(null);
    this.hoverLeft.set(null);
    this.hoverPrice.set(null);
  }

  private chartFor(pane: ChartPane): ApexCharts | null {
    if (pane === 'price') {
      return this.chartInstance();
    }
    if (pane === 'volume') {
      return this.volumeChartInstance();
    }
    return this.rsiChartInstance();
  }

  protected onPlotClick(event: MouseEvent): void {
    if (!this.drawing()) {
      return;
    }
    const target = event.target;
    if (target instanceof Element && target.closest('.apexcharts-toolbar, .apexcharts-legend')) {
      return;
    }
    const instance = this.chartInstance();
    if (!instance) {
      return;
    }
    const globals = (instance as unknown as ChartWithGlobals).w?.globals;
    if (!globals) {
      return;
    }
    const host = event.currentTarget;
    if (!(host instanceof HTMLElement)) {
      return;
    }
    const rect = host.getBoundingClientRect();
    const point = pixelToData(event.clientX - rect.left, event.clientY - rect.top, globals);
    if (!point) {
      return;
    }
    const snapped = nearestTime(point.x, this.candleTimes());
    if (snapped === null) {
      return;
    }
    this.addPoint(snapped, point.y);
  }

  protected onChartFocus(): void {
    if (this.drawing() && this.data().candles.length > 0) {
      this.moveKeyboardCursor(this.keyboardIndex() ?? this.data().candles.length - 1);
    }
  }

  protected onChartKeydown(event: KeyboardEvent): void {
    if (!this.drawing()) {
      return;
    }
    const candles = this.data().candles;
    if (candles.length === 0) {
      return;
    }
    const current = this.keyboardIndex() ?? candles.length - 1;
    switch (event.key) {
      case 'ArrowLeft':
        this.moveKeyboardCursor(Math.max(0, current - 1));
        break;
      case 'ArrowRight':
        this.moveKeyboardCursor(Math.min(candles.length - 1, current + 1));
        break;
      case 'Home':
        this.moveKeyboardCursor(0);
        break;
      case 'End':
        this.moveKeyboardCursor(candles.length - 1);
        break;
      case 'Enter':
      case ' ': {
        const candle = candles[current];
        if (candle) {
          this.addPoint(new Date(candle.t).getTime(), candle.c);
          this.moveKeyboardCursor(current);
        }
        break;
      }
      case 'Escape':
        this.drawing.set(false);
        this.pending.set(null);
        this.keyboardIndex.set(null);
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  private moveKeyboardCursor(index: number): void {
    this.keyboardIndex.set(index);
    this.hoveredIndex.set(index);
    this.hoverLeft.set(null);
    this.hoverPrice.set(null);
  }

  private addPoint(x: number, y: number): void {
    const first = this.pending();
    if (!first) {
      this.pending.set({ x, y });
      return;
    }
    this.trendLines.update((lines) => [...lines, { x1: first.x, y1: first.y, x2: x, y2: y }]);
    this.pending.set(null);
    this.drawing.set(false);
  }

  private priceYAxis(range: { min: number; max: number } | null) {
    const scale = range ? niceAxisScale(range.min, range.max) : null;
    const span = scale && scale.step > 0 ? scale.max - scale.min : undefined;
    const intervals = span !== undefined && scale ? Math.round(span / scale.step) : undefined;
    const palette = this.palette();
    return {
      min: scale?.min,
      max: scale?.max,
      stepSize: scale && scale.step > 0 ? scale.step : undefined,
      labels: {
        minWidth: 44,
        formatter: (value: number) => formatAxisTick(value, span, intervals),
        style: { colors: palette.text },
      },
      tooltip: { enabled: true },
    };
  }

  private volumeYAxis(maxVolume: number) {
    const scale = niceAxisScale(0, Math.max(maxVolume, 1), 2);
    const palette = this.palette();
    return {
      min: 0,
      max: scale.step > 0 ? scale.max : undefined,
      stepSize: scale.step > 0 ? scale.step : undefined,
      labels: {
        minWidth: 44,
        formatter: (value: number) => formatVolume(value),
        style: { colors: palette.text, fontSize: '9px' },
      },
      tooltip: { enabled: false },
    };
  }

  private maxVolumeOf(candles: Candle[]): number {
    return candles.reduce((max, candle) => Math.max(max, candle.v ?? 0), 0);
  }

  private scaleYToRange(minTime: number, maxTime: number): void {
    if (!Number.isFinite(minTime) || !Number.isFinite(maxTime)) {
      return;
    }
    const instance = this.chartInstance();
    if (!instance) {
      return;
    }
    const visible = this.data().candles.filter((candle) => {
      const time = new Date(candle.t).getTime();
      return time >= minTime && time <= maxTime;
    });
    const range = this.rangeFor(visible);
    if (!range) {
      return;
    }
    void instance.updateOptions({ yaxis: this.priceYAxis(range) }, false, false, false, false);
    this.updateVisiblePanes(minTime, maxTime);
  }

  private updateVisiblePanes(minTime: number, maxTime: number): void {
    if (!Number.isFinite(minTime) || !Number.isFinite(maxTime)) {
      return;
    }
    this.visibleRange.set({ min: minTime, max: maxTime });
    const visible = this.data().candles.filter((candle) => {
      const time = new Date(candle.t).getTime();
      return time >= minTime && time <= maxTime;
    });
    const volume = this.volumeChartInstance();
    if (volume) {
      void volume.updateOptions(
        {
          xaxis: { min: minTime, max: maxTime },
          yaxis: this.volumeYAxis(this.maxVolumeOf(visible)),
        },
        false,
        false,
        false,
        false,
      );
    }
    this.syncVisibleRange(this.rsiChartInstance(), minTime, maxTime);
  }

  private syncVisibleRange(chart: ApexCharts | null, minTime: number, maxTime: number): void {
    if (!chart) {
      return;
    }
    void chart.updateOptions({ xaxis: { min: minTime, max: maxTime } }, false, false, false, false);
  }

  private rangeFor(candles: Candle[]): { min: number; max: number } | null {
    return priceRange(candles);
  }

  private lineSeries(
    name: string,
    points: { t: string; value: number }[],
    color: string,
  ): ApexAxisChartSeries[number] {
    return {
      name,
      type: 'line',
      color,
      data: points.map((point) => ({
        x: new Date(point.t).getTime(),
        y: point.value,
      })),
    };
  }

  private levelAnnotations(): YAxisAnnotations[] {
    const palette = this.palette();
    const supports: YAxisAnnotations[] = this.data().support.map((level) => ({
      y: level,
      borderColor: palette.support,
      label: {
        text: `S ${formatPrice(level)}`,
        position: 'left',
        textAnchor: 'start',
        offsetX: 6,
        borderColor: palette.support,
        style: {
          background: palette.support,
          color: palette.labelText,
          fontSize: '10px',
        },
      },
    }));
    const resistances: YAxisAnnotations[] = this.data().resistance.map((level) => ({
      y: level,
      borderColor: palette.resistance,
      label: {
        text: `R ${formatPrice(level)}`,
        position: 'left',
        textAnchor: 'start',
        offsetX: 6,
        borderColor: palette.resistance,
        style: {
          background: palette.resistance,
          color: palette.labelText,
          fontSize: '10px',
        },
      },
    }));
    return [...supports, ...resistances];
  }
}
