
{ ... }: {
  #GIT
  programs.git = {
    enable = true;

    settings = {
      user = {
        name = "atMiaobo";
        email = "181526233+atMiaobo@users.noreply.github.com";
      };

      init.defaultBranch = "main";
    };
  };

  programs.gh = {
    enable = true;

    settings = {
      git_protocol = "https";
    };

    gitCredentialHelper.enable = true;
  };
}

