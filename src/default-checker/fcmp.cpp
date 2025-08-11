#include <fstream>
#include <cstring>

using namespace std;

bool StrictCompare(std::ifstream& f_ans, std::ifstream& f_usr) {
  constexpr size_t kBufSize = 65536;
  static char buf1[kBufSize], buf2[kBufSize];
  size_t pos = 0;
  while (f_ans) {
    f_ans.read(buf1, kBufSize);
    f_usr.read(buf2, kBufSize);
    if (f_ans.eof() != f_usr.eof() || f_ans.gcount() != f_usr.gcount()) {
      return false;
    }
    if (memcmp(buf1, buf2, f_ans.gcount()) != 0) {
      return false;
    }
    pos += f_usr.gcount();
  }
  return true;
}

int main(int argc, char *argv[]) {
    std::ifstream test_out(argv[2]), user_ans(argv[3]);
    return !StrictCompare(test_out, user_ans);
}
