"""Reproducible, static quantitative report; no demo values or app traffic."""

import math
import os
import platform
import re
import textwrap

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
import numpy as np

from report_data import LABELS, NAMES, finite, require_final

BLUE = '#245EA8'
LIGHT = '#DCE8F4'
ORANGE = '#C9672C'
INK = '#192E40'
MUTED = '#5E7080'
GRID = '#E3E9EF'
BACKGROUND = '#F8FAFC'
MIB = 1024**2


def number(value, precision=2):
    if not finite(value):
        return 'N/A'
    if 0 < abs(value) < .1:
        return f'{value:.3g}'
    return f'{value:,.{precision}f}'


def count(value):
    if not finite(value):
        return 'N/A'
    if abs(value) >= 1e6:
        return f'{value/1e6:.2f}M'
    if abs(value) >= 10000:
        return f'{value/1000:.1f}k'
    return f'{value:,.0f}'


def percent(value, precision=1):
    return number(value*100, precision)+'%' if finite(value) else 'N/A'


def triple(stats, divisor=1):
    return ' / '.join(number(stats.get(key)/divisor if finite(stats.get(key)) else None, 2)
                      for key in ('average', 'median', 'p95'))


def text_block(figure, x, y, text, width, size=10.5, color=MUTED, line_spacing=1.45):
    wrapped = '\n'.join(textwrap.fill(line, width=width, break_long_words=False,
                                     break_on_hyphens=False) if line else ''
                        for line in text.split('\n'))
    return figure.text(x, y, wrapped, ha='left', va='top', fontsize=size,
                       color=color, linespacing=line_spacing)


def axis_style(axis):
    axis.set_facecolor('white')
    axis.spines[['top', 'right', 'left']].set_visible(False)
    axis.spines['bottom'].set_color(GRID)
    axis.tick_params(axis='both', colors=MUTED, labelsize=10, length=0)
    axis.grid(axis='x', color=GRID, linewidth=.7, zorder=0)
    axis.set_ylim(6.6, -.6)


def distribution_chart(axis, runs, accessor, title, unit, divisor=1, labels=False):
    axis_style(axis)
    axis.set_title(title, loc='left', fontsize=15, color=INK, fontweight='bold', pad=16)
    values = [accessor(run) for run in runs]
    maximum = max((s[key]/divisor for s in values for key in ('average', 'median', 'p95')
                   if finite(s.get(key))), default=1)
    axis.set_xlim(0, maximum*1.28 if maximum else 1)
    for row, stats in enumerate(values):
        if not finite(stats.get('average')):
            axis.text(0, row, 'Unavailable', color=MUTED, fontsize=10, va='center')
            continue
        average = stats['average']/divisor
        axis.barh(row, average, height=.44, color=LIGHT, edgecolor=BLUE, linewidth=.8, zorder=2)
        axis.scatter([stats['median']/divisor], [row], s=24, color=INK, marker='o', zorder=4)
        axis.scatter([stats['p95']/divisor], [row], s=35, color=ORANGE, marker='D', zorder=4)
        axis.text(max(average, stats['p95']/divisor)+maximum*.025, row, number(average),
                  va='center', fontsize=10, color=INK)
    axis.set_yticks(range(7), [r['name'] for r in runs] if labels else ['']*7)
    axis.set_xlabel(unit, loc='left', fontsize=10, color=MUTED, labelpad=10)


def table(figure, position, rows, headers, widths, size=9.8):
    axis = figure.add_axes(position)
    axis.axis('off')
    result = axis.table(cellText=rows, colLabels=headers, colWidths=widths,
                        cellLoc='left', loc='center', bbox=[0, 0, 1, 1])
    result.auto_set_font_size(False)
    result.set_fontsize(size)
    for (row, column), cell in result.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(1.8)
        cell.PAD = .09
        if row == 0:
            cell.set_facecolor(INK)
            cell.set_text_props(color='white', weight='bold', va='center')
        else:
            cell.set_facecolor('#EDF3F8' if row % 2 else 'white')
            cell.set_text_props(color=INK, va='center')
    return result


def build_line(run):
    build = run['build']
    compiler = build.get('compiler', '')
    version = build.get('version', '')
    if run['label'].startswith('python'):
        detail = version.split(' (')[0]
        match = re.search(r'\[(GCC[^\]]+|Clang[^\]]+)\]', version)
        if match:
            detail += ' | '+match.group(1)
        elif compiler:
            detail += ' | '+compiler.splitlines()[0]
        if build.get('gil_enabled') is not None:
            detail += ' | GIL '+('on' if build['gil_enabled'] else 'off')
        if build.get('jit_enabled') is not None:
            detail += ' | JIT '+('on' if build['jit_enabled'] else 'off')
    else:
        detail = compiler.splitlines()[0] if compiler else 'Build detail unavailable'
        if build.get('standard'):
            detail += ' | '+build['standard']
        if run['label'] == 'go':
            detail += ' | native GC / HTTP / TLS'
    return run['name']+': '+detail


def render(bundle, path):
    require_final(bundle)
    by_label = {run['label']: run for run in bundle['runs']}
    runs = [by_label[label] for label in LABELS]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
        'axes.unicode_minus': False, 'savefig.facecolor': BACKGROUND})
    figure = plt.figure(figsize=(24, 22), facecolor=BACKGROUND, dpi=200)
    figure.text(.045, .966, 'r2t  |  Seven live runtime measurements', fontsize=31,
                fontweight='bold', color=INK, va='top')
    start = min(r['started_at'] for r in runs)
    end = max(r['effective_end'] for r in runs)
    from report_data import iso
    subtitle = (f"{iso(start)[:10]} to {iso(end)[:10]} UTC  |  One production worker at a time  |  "
                '24-hour cap per configuration  |  No replay or historical baseline')
    figure.text(.045, .936, subtitle, fontsize=12, color=MUTED, va='top')
    jobs = sum(r['jobs']['completed'] for r in runs if finite(r['jobs']['completed']))
    messages = sum(r['jobs']['counters'].get('telegram_messages', 0) for r in runs)
    hours = sum(r['exposure_seconds'] for r in runs)/3600
    terminal = sum(r['status'] == 'finished' for r in runs)
    figure.text(.045, .902,
        f'{number(hours, 1)} window hours     {count(jobs)} observed completed jobs     '
        f'{count(messages)} acknowledged Telegram messages     {terminal}/7 windows reached their deadline',
        fontsize=15, fontweight='bold', color=INK, va='top')
    figure.text(.045, .877,
        'Observed implementation results: workload, media mix, upstream latency, libraries and runtime builds differ between days.',
        fontsize=12, color=MUTED, va='top')

    cpu_axis = figure.add_axes([.093, .637, .245, .180])
    memory_axis = figure.add_axes([.405, .637, .245, .180])
    cost_axis = figure.add_axes([.718, .637, .235, .180])
    distribution_chart(cpu_axis, runs, lambda r: r['components']['application']['cpu']['sampled_percent_one_core'],
                       'Application CPU', '% of one core; 100% = one full core', labels=True)
    distribution_chart(memory_axis, runs, lambda r: r['components']['application']['memory_bytes'],
                       'Application memory', 'MiB; worker + helpers + scheduler cgroups', divisor=MIB)
    axis_style(cost_axis)
    cost_axis.set_title('CPU per completed job', loc='left', fontsize=15, color=INK, fontweight='bold', pad=16)
    costs = [r.get('cpu_seconds_per_completed_job') for r in runs]
    maximum = max((v for v in costs if finite(v)), default=1)
    cost_axis.set_xlim(0, maximum*1.3 if maximum else 1)
    for row, value in enumerate(costs):
        if finite(value):
            cost_axis.barh(row, value, height=.44, color=BLUE, zorder=2)
            cost_axis.text(value+maximum*.025, row, number(value), color=INK, va='center', fontsize=10)
        else:
            cost_axis.text(0, row, 'Unavailable', color=MUTED, fontsize=10, va='center')
    cost_axis.set_yticks(range(7), ['']*7)
    cost_axis.set_xlabel('Application CPU seconds / observed job end', loc='left', fontsize=10, color=MUTED, labelpad=10)
    handles = [Line2D([], [], color=BLUE, linewidth=6, label='Mean (number shown)'),
               Line2D([], [], color=INK, marker='o', linestyle='', label='Median'),
               Line2D([], [], color=ORANGE, marker='D', linestyle='', label='P95')]
    figure.legend(handles=handles, loc='upper left', bbox_to_anchor=(.043, .853), frameon=False,
                  ncol=3, fontsize=11, labelcolor=INK)

    figure.text(.045, .593, 'Workload, delivery and timing', fontsize=17, color=INK, fontweight='bold')
    workload_rows = []
    for run in runs:
        counters = run['jobs']['counters']
        available = run['jobs']['telemetry_available']
        sample_cover = percent(run['sampling_coverage_fraction'], 2)
        process_cover = percent(run['processes']['coverage_fraction'], 1)
        incoming = counters.get('http_response_body_bytes', 0)
        outgoing = counters.get('telegram_request_body_bytes', 0)
        workload_rows.append([run['name'], f"{run['exposure_seconds']/3600:.2f} h\nS {sample_cover} / P {process_cover}",
            count(run['jobs']['completed']), percent(run['jobs']['success_fraction']),
            count(counters.get('telegram_messages', 0) if available else None),
            (count(counters.get('telegram_messages_video', 0))+' / '+count(counters.get('telegram_messages_photo', 0))) if available else 'N/A',
            (number(incoming/MIB, 1)+' / '+number(outgoing/MIB, 1)) if available else 'N/A',
            triple(run['jobs']['processing_seconds']), triple(run['jobs']['queue_wait_seconds']),
            count(run['queued_backlog']['maximum'])])
    table(figure, [.043, .391, .914, .180], workload_rows,
          ['Runtime', 'Exposure / coverage', 'Jobs', 'Task\nsuccess', 'TG msgs', 'Video /\nphoto msgs',
           'Body MiB\nHTTP read / TG write', 'Job seconds\nmean / med / P95', 'Queue seconds\nmean / med / P95', 'Queue\nmax'],
          [.106, .139, .064, .071, .070, .080, .112, .145, .145, .068], size=9.4)
    figure.text(.045, .378,
        'S = complete cgroup sampling coverage; P = supplementary process-split coverage. Task success is not delivery success. '
        'Body read excludes Telegram responses; body write covers Telegram requests. TLS/framing and remote URL downloads are excluded.',
        fontsize=9.5, color=MUTED)

    figure.text(.045, .346, 'Memory throughout each window', fontsize=16, color=INK, fontweight='bold')
    heat_axis = figure.add_axes([.093, .210, .340, .118])
    matrix = np.asarray([[v/MIB if finite(v) else np.nan for v in r['hourly_application_memory_bytes']]
                         for r in runs], dtype=float)
    cmap = LinearSegmentedColormap.from_list('r2t_memory', ['#EDF3F9', '#8FB6DB', BLUE])
    cmap.set_bad('#D4DAE0')
    if np.isfinite(matrix).any():
        image = heat_axis.imshow(np.ma.masked_invalid(matrix), aspect='auto', cmap=cmap,
            vmin=0, vmax=max(1, float(np.nanmax(matrix))), extent=(0, 24, 6.5, -.5), interpolation='nearest')
        color_axis = figure.add_axes([.448, .210, .010, .118])
        colorbar = figure.colorbar(image, cax=color_axis)
        colorbar.ax.tick_params(labelsize=9, colors=MUTED, length=0)
        colorbar.outline.set_visible(False)
        colorbar.set_label('Hourly mean MiB', fontsize=9, color=MUTED, labelpad=10)
    heat_axis.set_yticks(range(7), [r['name'] for r in runs], color=MUTED, fontsize=10)
    heat_axis.set_xticks([0, 6, 12, 18, 24], ['0', '6', '12', '18', '24'])
    heat_axis.set_xlabel('Elapsed hours; gray = no observation', loc='left', fontsize=10, color=MUTED, labelpad=8)
    heat_axis.tick_params(length=0, colors=MUTED)
    heat_axis.spines[:].set_visible(False)

    figure.text(.525, .346, 'CPU components and sampled memory', fontsize=16, color=INK, fontweight='bold')
    component_rows = []
    for run in runs:
        process = run['processes']
        worker_cpu = process.get('worker_cpu_percent_one_core', {}).get('average')
        helper_cpu = process.get('helpers_cpu_percent_one_core', {}).get('average')
        ffmpeg = process.get('roles', {}).get('ffmpeg', {})
        ffmpeg_max = ffmpeg.get('rss_bytes', {}).get('maximum')
        ffmpeg_text = number(ffmpeg_max/MIB, 1) if finite(ffmpeg_max) and ffmpeg.get('samples_with_live_process', 0) else 'Not seen'
        component_rows.append([run['name'], number(worker_cpu), number(helper_cpu),
            number(run['components']['scheduler']['cpu']['sampled_percent_one_core']['average']),
            number(run['components']['mongodb']['cpu']['sampled_percent_one_core']['average']),
            ffmpeg_text, number(run['components']['combined']['memory_bytes']['p95']/MIB, 1)
            if finite(run['components']['combined']['memory_bytes']['p95']) else 'N/A'])
    table(figure, [.523, .210, .434, .118], component_rows,
          ['Runtime', 'Parent\nCPU %*', 'Helpers\nCPU %*', 'Scheduler\nCPU %', 'MongoDB\nCPU %', 'FFmpeg\nmax RSS*', 'Combined\nP95 MiB'],
          [.18, .13, .13, .14, .13, .14, .15], size=9.0)
    text_block(figure, .525, .198,
        '* Process split uses P coverage above. Helpers include ffmpeg and maintenance subprocesses; '
        'short ffmpeg lifetimes can be missed. FFmpeg RSS is the maximum seen in five-second snapshots, in MiB.',
        width=110, size=9.2)

    figure.text(.045, .162, 'Runtime builds', fontsize=15, color=INK, fontweight='bold')
    build_text = '\n'.join(build_line(run) for run in runs)
    text_block(figure, .045, .149, build_text, width=92, size=9.7, line_spacing=1.5)
    figure.text(.525, .162, 'How to read the comparison', fontsize=15, color=INK, fontweight='bold')
    limits = [
        'One fresh live window per configuration. Differences describe these deployments and days; they do not isolate language speed.',
        'P95 is nearest rank, not a confidence interval. CPU distributions use intervals up to 10 seconds; memory includes cgroup file cache. Kernel lifetime peaks are kept separately in comparison.json.',
        'Processing and queue timings require paired in-window start/end events. Incomplete boundary jobs are censored. CPU/job still includes application work from incomplete jobs.',
    ]
    if any(n['event'] == 'deployment_environment_correction' for r in runs for n in r['notes']):
        limits.append('Python 3.12: the first accounted cron call failed due to a missing user-bus environment. The cron environment was corrected; the window was not restarted.')
    if any(r['source_changed'] for r in runs):
        limits.append('At least one run changed tracked source or configuration during observation; inspect its source_changed flag before comparing results.')
    if any(r['status'] != 'finished' for r in runs):
        limits.append('At least one window ended early or failed to launch. Exposure and unavailable values remain visible; no missing result is shown as zero.')
    if any(r['components']['application']['cpu']['counter_reset_intervals'] for r in runs):
        limits.append('CPU counter resets were observed. The affected CPU totals omit unresolvable intervals and must be treated as incomplete.')
    text_block(figure, .525, .149, '\n\n'.join(limits), width=112, size=9.5, line_spacing=1.35)
    figure.text(.045, .018,
        'Evidence: comparison.json, distributions.csv, windows.csv, counters.csv and original-file SHA-256 receipts. '
        'Separate process observations began partway through Python 3.12; no earlier process split is inferred.',
        fontsize=9.4, color=MUTED)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    outside = []
    for index, artist in enumerate(figure.texts):
        bounds = artist.get_window_extent(renderer)
        if bounds.x0 < 0 or bounds.y0 < 0 or bounds.x1 > figure.bbox.x1 or bounds.y1 > figure.bbox.y1:
            outside.append(index)
    if outside:
        plt.close(figure)
        raise ValueError('Report text extends outside the image; adjust layout before export')
    temporary = path.with_name(path.stem+f'.{os.getpid()}.png')
    figure.savefig(temporary, dpi=200, format='png', facecolor=BACKGROUND,
                   metadata={'Title': 'r2t live runtime comparison', 'Description': 'Seven fresh sequential live windows; see comparison.json for evidence and limits.'})
    temporary.replace(path)
    size = tuple(int(v) for v in figure.canvas.get_width_height())
    plt.close(figure)
    return dict(python=platform.python_version(), matplotlib=matplotlib.__version__,
                numpy=np.__version__, pixels=list(size), dpi=200,
                figure_text_inside_canvas=True, rendered_visual_inspection='pending')
