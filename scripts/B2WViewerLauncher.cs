// Start the project viewer on the user's interactive Windows desktop.
// The argument file has one literal argument per line and stays in this project.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class B2WViewerLauncher
{
    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        using var form = new Form
        {
            Text = "B2W viewer launcher",
            Width = 430,
            Height = 115,
            StartPosition = FormStartPosition.CenterScreen,
        };
        var label = new Label { Text = "Starting B2W viewer...", Dock = DockStyle.Fill, TextAlign = System.Drawing.ContentAlignment.MiddleCenter };
        form.Controls.Add(label);
        form.Shown += (_, _) =>
        {
            string root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, ".."));
            string cache = Path.Combine(root, ".cache");
            string log = Path.Combine(cache, "b2w-viewer-launcher.log");
            try
            {
                string argumentFile = Path.Combine(cache, "b2w-viewer-args.txt");
                string python = @"D:\isaacsim51\Scripts\pythonw.exe";
                if (!File.Exists(argumentFile) || !File.Exists(python))
                    throw new FileNotFoundException("Viewer argument file or Python runtime is missing");
                string[] arguments = File.ReadAllLines(argumentFile);
                if (arguments.Length < 5 || arguments[0] != "scripts/view_b2w_gamepad_3d.py")
                    throw new InvalidDataException("Unexpected viewer argument file");

                var start = new ProcessStartInfo(python)
                {
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = false,
                    RedirectStandardError = true,
                    RedirectStandardOutput = true,
                };
                foreach (string argument in arguments)
                    start.ArgumentList.Add(argument);
                Process child = Process.Start(start) ?? throw new InvalidOperationException("Python viewer did not start");
                File.WriteAllText(log, $"VIEWER_PID={child.Id}{Environment.NewLine}");
                var started = DateTime.UtcNow;
                var timer = new Timer { Interval = 500 };
                timer.Tick += (_, _) =>
                {
                    if (child.HasExited)
                    {
                        timer.Stop();
                        File.WriteAllText(Path.Combine(cache, "b2w-viewer-interactive-stderr.log"), child.StandardError.ReadToEnd());
                        File.WriteAllText(Path.Combine(cache, "b2w-viewer-interactive-stdout.log"), child.StandardOutput.ReadToEnd());
                        File.AppendAllText(log, $"VIEWER_EXIT={child.ExitCode}{Environment.NewLine}");
                        label.Text = "Viewer failed. See .cache/b2w-viewer-interactive-stderr.log";
                        child.Dispose();
                    }
                    else if ((DateTime.UtcNow - started).TotalSeconds >= 8)
                    {
                        timer.Stop();
                        child.Dispose();
                        form.Close();
                    }
                };
                timer.Start();
            }
            catch (Exception exception)
            {
                File.WriteAllText(log, exception.ToString());
                label.Text = "Viewer failed. See .cache/b2w-viewer-launcher.log";
            }
        };
        Application.Run(form);
    }
}
