import re
import subprocess
from pathlib import Path

from conan import ConanFile
from conan.errors import ConanException
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout
from conan.tools.files import copy, load, rmdir


class Open62541LogicmeltConan(ConanFile):
    # The CMake project is named "open62541"; the package is deliberately named
    # differently so this fork can never resolve in place of conancenter's open62541.
    # package_info() maps the CMake identity back, so consumers are unaffected.
    name = "open62541-logicmelt"
    # Fail the graph if conancenter's open62541 is pulled in too, rather than
    # silently linking two libopen62541 with identical headers.
    provides = "open62541"
    package_type = "library"

    license = "MPL-2.0"
    author = "Logicmelt <info@logicmelt.com>"
    url = "https://github.com/logicmelt/open62541"
    description = (
        "Logicmelt fork of open62541 with optimized subscription "
        "value-change detection."
    )
    topics = ("opcua", "iec62541", "industrial")

    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": True, "fPIC": True}

    # Only what the build compiles or installs. doc/ and README.md look removable
    # but configure fails without them. deps/* patterns are recursive, so each
    # submodule needs an explicit negation.
    exports_sources = (
        "CMakeLists.txt",
        "src/*",
        "include/*",
        "plugins/*",
        "arch/*",
        "tools/*",
        "doc/*",
        "README.md",
        "LICENSE*",
        "deps/*.c",
        "deps/*.h",
        "!deps/mdnsd/*",
        "!deps/mqtt-c/*",
        "!deps/ua-nodeset/*",
    )

    def _load_cmakelists(self):
        return load(self, Path(self.recipe_folder) / "CMakeLists.txt")

    def set_version(self):
        # <upstream MAJOR.MINOR.PATCH>.<Logicmelt revision>, e.g. 1.3.6.2. The 4th
        # component sorts above a bare 1.3.6 and stays inside [>=1.3.6 <1.4.0], so
        # fork revisions are pinnable; a pre-release suffix would sort below it and
        # be excluded from ranges. Upstream's project() carries no VERSION, so the
        # template's regex does not apply here.
        cmake_content = self._load_cmakelists()

        parts = []
        for variable in (
            "OPEN62541_VER_MAJOR",
            "OPEN62541_VER_MINOR",
            "OPEN62541_VER_PATCH",
            "LOGICMELT_VER_REVISION",
        ):
            match = re.search(rf"set\({variable}\s+([0-9]+)\)", cmake_content)
            if not match:
                raise ConanException(f"Cannot extract {variable} from CMakeLists.txt")
            parts.append(match.group(1))
        base_version = ".".join(parts)

        def git(*args: str) -> str:
            return subprocess.check_output(
                ["git", *args],
                cwd=self.recipe_folder,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

        # Fall back to the bare base version if git is unavailable (no repo or
        # binary, shallow clone without history, etc.).
        try:
            branch = git("rev-parse", "--abbrev-ref", "HEAD")
            count = git("rev-list", "--count", "HEAD")
        except (subprocess.CalledProcessError, OSError):
            self.version = base_version
            return

        # Release tags are v<MAJOR>.<MINOR>.<PATCH>-logicmelt<REV>, e.g. v1.3.6-logicmelt2.
        # The "-logicmelt" infix is what excludes upstream's own tags, which are
        # v-prefixed too (v1.3.6, and 4-component ones like v1.3.3.1).
        try:
            tag = git("describe", "--tags", "--exact-match", "--match", "v*-logicmelt*")
        except subprocess.CalledProcessError:
            tag = None

        if tag is not None:
            # A release tag must agree with CMakeLists.txt. A mismatch means a
            # forgotten LOGICMELT_VER_REVISION bump, so the build should fail.
            tag_match = re.fullmatch(
                r"v([0-9]+\.[0-9]+\.[0-9]+)-logicmelt([0-9]+)", tag
            )
            if not tag_match:
                raise ConanException(
                    f"Release tag '{tag}' is not of the form "
                    f"v<MAJOR>.<MINOR>.<PATCH>-logicmelt<REV>."
                )
            tag_version = f"{tag_match.group(1)}.{tag_match.group(2)}"
            if tag_version != base_version:
                raise ConanException(
                    f"Release tag '{tag}' implies version '{tag_version}', which does "
                    f"not match OPEN62541_VER_*/LOGICMELT_VER_REVISION '{base_version}' "
                    f"in CMakeLists.txt."
                )
            self.version = base_version
        elif branch == "logicmelt-master":
            # The fork's release branch, equivalent to master elsewhere. This
            # repo's own master tracks upstream open62541, so master is
            # deliberately NOT the release branch.
            self.version = base_version
        elif branch.startswith("release/"):
            self.version = f"{base_version}-rc.{count}"
        else:
            # Detached HEAD reports as the literal "HEAD"
            if branch == "HEAD":
                safe_branch = "detached"
            else:
                safe_branch = re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()
                safe_branch = safe_branch or "unknown"
            self.version = f"{base_version}-branch.{safe_branch}.{count}"

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")
        # C99 library: its ABI cannot depend on C++ settings. Keeping them would
        # give every consumer C++ profile its own byte-identical binary.
        self.settings.rm_safe("compiler.cppstd")
        self.settings.rm_safe("compiler.libcxx")

    def layout(self):
        cmake_layout(self)

    def generate(self):
        tc = CMakeToolchain(self)

        # Reproduces the feature set the library was already built with, so moving
        # to Conan is not also a behaviour change. Pinned explicitly rather than
        # left to upstream defaults, which change between versions.
        tc.cache_variables["UA_ENABLE_SUBSCRIPTIONS"] = True
        tc.cache_variables["UA_ENABLE_SUBSCRIPTIONS_EVENTS"] = True
        tc.cache_variables["UA_ENABLE_METHODCALLS"] = True
        tc.cache_variables["UA_ENABLE_NODEMANAGEMENT"] = True
        tc.cache_variables["UA_ENABLE_PARSING"] = True
        tc.cache_variables["UA_ENABLE_DA"] = True
        tc.cache_variables["UA_ENABLE_STATUSCODE_DESCRIPTIONS"] = True
        tc.cache_variables["UA_ENABLE_TYPEDESCRIPTION"] = True
        tc.cache_variables["UA_ENABLE_HARDENING"] = True

        tc.cache_variables["UA_ENABLE_PUBSUB"] = False
        # Leaving this on while PubSub is off makes CMake abort, so it must go too.
        tc.cache_variables["UA_ENABLE_PUBSUB_INFORMATIONMODEL"] = False
        tc.cache_variables["UA_ENABLE_HISTORIZING"] = False
        tc.cache_variables["UA_ENABLE_DISCOVERY"] = False
        tc.cache_variables["UA_ENABLE_DISCOVERY_MULTICAST"] = False
        tc.cache_variables["UA_ENABLE_JSON_ENCODING"] = False
        tc.cache_variables["UA_ENABLE_DIAGNOSTICS"] = False

        # Amalgamation makes install() abort, and the extra targets are not packaged.
        tc.cache_variables["UA_ENABLE_AMALGAMATION"] = False
        tc.cache_variables["UA_BUILD_EXAMPLES"] = False
        tc.cache_variables["UA_BUILD_UNIT_TESTS"] = False
        tc.cache_variables["UA_BUILD_TOOLS"] = False
        tc.cache_variables["UA_FORCE_WERROR"] = False

        # REDUCED keeps UA_SCHEMA_DIR pointed at tools/schema, which is why
        # deps/ua-nodeset is never read and need not be exported. Changing this
        # to FULL requires updating exports_sources as well.
        tc.cache_variables["UA_NAMESPACE_ZERO"] = "REDUCED"

        tc.generate()

        # No CMakeDeps here on purpose: it writes the find_package() config files
        # for a recipe's dependencies, and this package has none.

    def build(self):
        # This build never compiles deps/ua-nodeset (90 MB), so it is not exported.
        # CMake still installs that directory unconditionally, with no option to
        # skip it, so cmake.install() would fail on the missing path.
        # An empty directory is enough to satisfy it.
        Path(self.source_folder, "deps", "ua-nodeset").mkdir(
            parents=True, exist_ok=True
        )

        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        # The recipe declares license = "MPL-2.0"; ship the licence texts.
        copy(
            self,
            "LICENSE*",
            src=self.source_folder,
            dst=str(Path(self.package_folder) / "licenses"),
        )
        # Consumers get their CMake config and pkg-config from Conan, so the ones
        # open62541 installs here are never read.
        rmdir(self, str(Path(self.package_folder) / "lib" / "cmake"))
        rmdir(self, str(Path(self.package_folder) / "lib" / "pkgconfig"))
        # share/ holds the nodeset compiler and schemas (~3 MB), unusable through
        # Conan and not needed to link against the library.
        rmdir(self, str(Path(self.package_folder) / "share"))

    def package_info(self):
        self.cpp_info.libs = ["open62541"]
        # Map the CMake identity back to upstream's name so consumers write
        # find_package(open62541) and link open62541::open62541 unchanged.
        self.cpp_info.set_property("cmake_file_name", "open62541")
        self.cpp_info.set_property("cmake_target_name", "open62541::open62541")

        if self.settings.os in ("Linux", "FreeBSD"):
            # Consumers must link pthread themselves. m and rt are only needed for
            # a static build, since a shared library already resolves them.
            self.cpp_info.system_libs = ["pthread"]
            if not self.options.shared:
                self.cpp_info.system_libs.extend(["m", "rt"])
